import hashlib
import json
import sys
from decimal import Decimal
from pathlib import Path

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services import question_charts
from scripts.redraw_charts import ROOT, load_charts, render_all


def test_transcribed_exam_chart_values_categories_and_precision():
    charts={Path(c["image"]).stem:c for c in load_charts()}
    expected={
        "ky2_2020":(["消磨时间","学习知识","获取信息","其他"],[21.3,59.5,17,2.2]),
        "ky2_2021":(["独自锻炼","和朋友一起","和家人一起","团体活动"],[54.3,47.7,23.9,15.8]),
        "ky2_2024":(["提升了动手能力","学习了相关知识","提升了合作能力","感觉到心情舒畅"],[84.8,91.3,32.6,54.4]),
        "ky2_2025":(["看电视","散步","养花","阅读","下棋"],[90.8,68.3,34.7,31.8,18.4]),
        "ky2_2026":(["满足好奇心","促进观察力","强身健体","增强亲子互动"],[54.6,54.5,37.2,33.2]),
    }
    for name,(categories,values) in expected.items():
        assert charts[name]["categories"]==categories
        assert charts[name]["values"]==values
    assert sum(Decimal(str(v)) for v in charts["ky2_2020"]["values"])==100
    delivery=charts["ky2_2022"]
    assert delivery["categories"]==["2018年","2019年","2020年"]
    assert delivery["series"]==[{"name":"总体","values":[51,64,83]},{"name":"农村","values":[12,15,30]}]
    assert "10亿件" in delivery["title"]
    assert charts["ky2_2023"]["values"]==[8.8,9.48,9.79,10.25,11.58,14.18,17.06,19.17,23.15,25.4]
    for chart in charts.values():
        for value,label in zip(chart.get("values",[]),chart.get("labels",[])):
            if label: assert Decimal(label.rstrip('%'))==Decimal(str(value))


def test_two_statistical_graphs_preserve_units_axes_and_hide_unprinted_numbers():
    urban,education,poverty=load_charts()[:3]
    assert urban["years"]==[1980,1985,1990,1995,2000,2005,2010,2011,2012,2013,2014,2015,2016,2017,2018,2019]
    assert urban["ylim"]==[10,70]
    for year,value in [(2012,52.57),(2014,54.77),(2017,58.52)]:
        index=urban["years"].index(year)
        assert urban["values"][index]==value and urban["labels"][index]==""
    assert len(urban["references"])==3
    assert education["years"][0]==1990 and education["years"][-1]==2019
    assert len(education["years"])==len(education["values"])==22
    assert education["values"]==[3.4,6.86,12.5,13.3,15,17,19,21,22,23,23.3,24.2,26.5,26.9,30,34.5,37.5,40,42.7,45.7,48.1,51.6]
    assert poverty["population_million"]==[98.99,82.49,70.17,55.75,43.35,30.46,16.6,5.51,0]
    assert poverty["ratio"]==[10.2,8.5,7.2,5.7,4.5,3.1,1.7,.6,0]
    assert poverty["labels"]==[""]*8+["0"]
    assert poverty["ylim"]==[0,100] and poverty["right_ylim"]==[0,12]
    assert all(url.startswith("https://www.stats.gov.cn/") for url in poverty["references"])


def test_chart_sources_and_reusable_outputs_are_complete_and_originals_unchanged(tmp_path):
    charts=load_charts()
    assert len(charts)==10
    before={c["original_image"]:hashlib.sha256((ROOT/'backend/data'/c["original_image"]).read_bytes()).hexdigest() for c in charts}
    render_all(tmp_path)
    for chart in charts:
        assert hashlib.sha256((ROOT/chart["source_file"]).read_bytes()).hexdigest()==chart["source_sha256"]
        assert before[chart["original_image"]]==chart["original_sha256"]
        assert hashlib.sha256((tmp_path/chart["original_image"]).read_bytes()).hexdigest()==chart["original_sha256"]
        png=tmp_path/chart["image"]
        svg=png.with_suffix('.svg').read_text(encoding='utf-8')
        with Image.open(png) as image:
            assert image.width>=1900 and image.height>=1100
        assert '<svg' in svg and '<image' not in svg  # 矢量路径，不能把旧扫描图嵌进去冒充重绘。
        for label in chart.get("labels",[]):
            if label: assert label in svg
        assert chart["title"] in svg
        if chart["kind"]=='grouped_bar':
            assert '总体' in svg and '农村' in svg
    after={c["original_image"]:hashlib.sha256((ROOT/'backend/data'/c["original_image"]).read_bytes()).hexdigest() for c in charts}
    assert before==after


def test_question_api_media_uses_svg_but_retains_png_and_original_fallback(tmp_path,monkeypatch):
    monkeypatch.setattr(question_charts,'DATA_DIR',str(tmp_path))
    image=tmp_path/'charts/example.png'; image.parent.mkdir(); image.write_bytes(b'png')
    assert question_charts.chart_assets('charts/example.png')=={}
    image.with_suffix('.svg').write_text('<svg/>')
    original=image.parent/'originals'/image.name; original.parent.mkdir(); original.write_bytes(b'original')
    assert question_charts.chart_assets('charts/example.png')=={
        'chart_display_image':'charts/example.svg','chart_original_image':'charts/originals/example.png',
    }
    for path in ('','/etc/passwd','charts/../speech-cache/file.png'):
        assert question_charts.chart_assets(path)=={}
