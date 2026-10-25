"""依据逐项核对的数据重绘真题图表，同时保留原卷裁图用于对照。"""
import hashlib
import io
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "backend/data/chart_redraws.json"


def load_charts():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))["charts"]


def _font():
    from matplotlib import font_manager
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in ("Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "WenQuanYi Zen Hei"):
        if name in available:
            return name
    raise RuntimeError("重绘中文图表需要微软雅黑、思源黑体或其他受支持的中文字体")


def draw_chart(spec):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    from matplotlib.ticker import FuncFormatter
    import numpy as np

    long = spec["kind"] in ("urbanization", "education")
    note = bool(spec.get("footnote"))
    fig, ax = plt.subplots(figsize=(15 if long else 11, 7.8 if note else 6.4))
    fig.subplots_adjust(left=.11 if spec["kind"] != "horizontal_bar" else .24,
                        right=.89 if spec["kind"] == "poverty" else .96,
                        top=.83 if spec["kind"] == "poverty" else .87,
                        bottom=.31 if spec["kind"] == "education" else (.34 if note else .19))
    bottom_title = spec.get("title_position") == "bottom"
    if bottom_title:
        fig.text(.52,.19 if note else .055,spec["title"],ha="center",va="center",fontsize=18)
    else:
        fig.suptitle(spec["title"],fontsize=19,y=.97)
    if note:
        fig.text(.08,.055 if spec["kind"] == "line" else .065,spec["footnote"],fontsize=12,ha="left",va="bottom",linespacing=1.8)
    ax.spines[["top","right"]].set_visible(False)
    ax.tick_params(labelsize=12)
    gray, line = "#a1a1a1", "#303030"
    kind = spec["kind"]
    if kind == "pie":
        values = spec["values"]
        wedges, _ = ax.pie(values,startangle=90,counterclock=False,
                          colors=["#bdbdbd","#757575","#dedede","#f2f2f2"],
                          wedgeprops={"edgecolor":"#555555","linewidth":1.2})
        label_positions=[(1.35,.85),(.55,-1.26),(-1.4,.55),(-.12,1.25)]
        for wedge, category, label, position in zip(wedges,spec["categories"],spec["labels"],label_positions):
            angle=np.deg2rad((wedge.theta1+wedge.theta2)/2)
            x,y=np.cos(angle),np.sin(angle)
            ax.annotate(category+"\n"+label,xy=(x*.94,y*.94),xytext=position,
                        ha="center",va="center",fontsize=15,
                        arrowprops={"arrowstyle":"-","color":"#555555","connectionstyle":f"angle,angleA=0,angleB={np.rad2deg(angle)}"},
                        bbox={"boxstyle":"square,pad=.35","fc":"white","ec":"#888888"})
        ax.set_xlim(-2.05,2.05); ax.set_ylim(-1.5,1.5)
        return fig
    if kind == "horizontal_bar":
        x=np.arange(len(spec["categories"]))
        bars=ax.barh(x,spec["values"],height=.47,color=gray,edgecolor="#666666",linewidth=.7)
        ax.set_yticks(x,spec["categories"]); ax.invert_yaxis()
        ax.set_xlim(spec["ylim"]); ax.set_xticks(np.arange(0,101,20))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v,p:f"{v:.0f}%"))
        ax.spines["left"].set_visible(False)
        for bar,label in zip(bars,spec["labels"]):
            ax.text(bar.get_width()+1.4,bar.get_y()+bar.get_height()/2,label,va="center",fontsize=13)
        return fig
    if kind == "grouped_bar":
        x=np.arange(len(spec["categories"]))
        for index,series in enumerate(spec["series"]):
            bars=ax.bar(x+(index-.5)*.29,series["values"],width=.29,color=gray if index==0 else "white",
                        hatch=None if index==0 else "////",edgecolor="#666666",label=series["name"])
            for bar,value in zip(bars,series["values"]):
                ax.annotate(str(value),(bar.get_x()+bar.get_width()/2,value),xytext=(0,7),textcoords="offset points",ha="center",fontsize=15)
        ax.set_xticks(x,spec["categories"])
        ax.legend(frameon=False,fontsize=14,loc="upper right",bbox_to_anchor=(1,.9))
        ax.set_xlim(-.6,3.3)
    elif kind in ("urbanization","education","line"):
        x=np.arange(len(spec["years"])); values=spec["values"]
        if kind == "education":
            ax.bar(x,values,color="#cccccc",edgecolor="#888888",width=.55,zorder=2)
        elif kind == "urbanization":
            # 原卷的灰色竖条是背景条纹，不是另一组数据柱。
            for pos in x[::2]: ax.axvspan(pos-.28,pos+.28,color="#eeeeee",zorder=0)
        ax.plot(x,values,"o-",color=line,linewidth=2,markersize=4.5,zorder=3)
        for index,(pos,value,label) in enumerate(zip(x,values,spec["labels"])):
            if label:
                offset=9 if kind!="education" else (9 if index%2==0 else 25)
                if kind=="urbanization" and index>6: offset=10 if index%2 else 25
                ax.annotate(label,(pos,value),xytext=(0,offset),textcoords="offset points",ha="center",fontsize=11 if long else 12)
        ax.set_xticks(x,[str(y) for y in spec["years"]],rotation=45 if kind=="education" else 0)
        ax.set_xlim(-.6,len(x)-.4)
        ticks=np.arange(10,71,10) if kind=="urbanization" else (np.arange(0,61,15) if kind=="education" else np.arange(0,31,5))
        ax.set_yticks(ticks); ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f"{v:.0f}%"))
        ax.grid(axis="y",color="#d3d3d3",linestyle=":" if kind=="education" else "-",linewidth=.8,zorder=0)
    elif kind == "poverty":
        x=np.arange(len(spec["years"]))
        ax.bar(x,spec["population_million"],color="#bdbdbd",edgecolor="#777777",width=.52)
        right=ax.twinx()
        right.plot(x[:-1],spec["ratio"][:-1],"o-",color=line,linewidth=2,markersize=5)
        right.plot(x[-2:],spec["ratio"][-2:],"o--",color=line,linewidth=2,markersize=5)
        right.set_ylim(spec["right_ylim"]); right.set_yticks([0,3,6,9,12]); right.tick_params(labelsize=12)
        right.spines["top"].set_visible(False)
        ax.text(0,1.03,"(Million people)",transform=ax.transAxes,fontsize=13)
        ax.text(1,1.03,"poverty headcount ratio\n(% of rural population)",transform=ax.transAxes,ha="right",fontsize=13)
        ax.set_xticks(x,[str(y) for y in spec["years"]]); ax.set_yticks([0,25,50,75,100])
        ax.set_xlim(-.6,len(x)-.4)
        ax.annotate("0",(x[-1],0),xytext=(0,7),textcoords="offset points",ha="center",fontsize=12)
        ax.grid(axis="y",color="#d3d3d3",linewidth=.8)
    else:
        x=np.arange(len(spec["categories"]))
        bars=ax.bar(x,spec["values"],color=gray,width=.55,edgecolor="#666666",linewidth=.7)
        ax.set_xticks(x,spec["categories"])
        for bar,label in zip(bars,spec["labels"]):
            ax.annotate(label,(bar.get_x()+bar.get_width()/2,bar.get_height()),xytext=(0,9),textcoords="offset points",ha="center",fontsize=14)
        if spec.get("percent_axis"):
            ax.set_yticks(np.arange(0,61,10)); ax.yaxis.set_major_formatter(FuncFormatter(lambda v,p:f"{v:.2f}%"))
        if spec.get("hide_y_labels"):
            ax.set_yticks([]); ax.spines["left"].set_visible(False)
        if spec.get("grid"):
            for value in np.arange(0,101,10): ax.axhline(value,color="#dddddd",zorder=0,linewidth=.8)
    ax.set_ylim(spec["ylim"])
    return fig


def render_all(output=None):
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    output=Path(output or ROOT/"backend/data")
    with matplotlib.rc_context({"font.family":_font(),"axes.unicode_minus":False,"svg.fonttype":"path","svg.hashsalt":"exam-charts-v1"}):
        for spec in load_charts():
            source=ROOT/spec["source_file"].replace("\\","/")
            original=ROOT/"backend/data"/spec["original_image"]
            if hashlib.sha256(source.read_bytes()).hexdigest()!=spec["source_sha256"]:
                raise ValueError(f"原卷已改变，不能继续使用旧重绘数据：{spec['source_file']}")
            if hashlib.sha256(original.read_bytes()).hexdigest()!=spec["original_sha256"]:
                raise ValueError(f"原卷裁图已改变，请重新核对：{spec['original_image']}")
            original_output=output/spec["original_image"]
            if original_output.resolve()!=original.resolve():
                original_output.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(original,original_output)
            fig=draw_chart(spec)
            for ext in ("png","svg"):
                target=(output/spec["image"]).with_suffix('.'+ext)
                target.parent.mkdir(parents=True,exist_ok=True)
                data=io.BytesIO()
                fig.savefig(data,format=ext,dpi=180,facecolor="white",metadata={"Date":None} if ext=="svg" else None)
                temporary=target.with_suffix(target.suffix+".tmp")
                temporary.write_bytes(data.getvalue()); os.replace(temporary,target)
            plt.close(fig)


if __name__=="__main__":
    render_all()
    print("已生成 10 张清晰图表（PNG 与 SVG），原卷裁图保持不变。")
