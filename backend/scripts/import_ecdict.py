"""从 ECDICT CSV 生成词书：
- 六级词书 (cet6)：tag 含 cet6
- 考研词书 (kaoyan)：tag 含 ky
- 短语书 (exam phrases)：ECDICT 多词词条(高频) + 内置核心考试短语
输出 data/words.json 与 data/phrases.json，由 seed.py 入库。
"""
import csv
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CSV_PATH = os.path.join(ROOT, "backend", "data", "ecdict.csv")
OUT_DIR = os.path.join(ROOT, "backend", "data")

# 内置核心考试短语（六级/考研高频动介搭配与习语）
CORE_PHRASES = [
    ("account for", "解释；占比；导致"), ("accuse sb. of sth.", "指控某人某事"),
    ("adapt to", "适应"), ("add to", "增加；增添"), ("adhere to", "坚持；遵守"),
    ("adjust to", "调整以适应"), ("be addicted to", "沉溺于"), ("allow for", "考虑到；为…留出余地"),
    ("amount to", "总计；等于"), ("answer for", "对…负责"), ("appeal to", "吸引；上诉；呼吁"),
    ("apply for", "申请"), ("apply to", "适用于"), ("approve of", "赞成；批准"),
    ("argue about/over", "争论"), ("arise from", "由…引起"), ("arrive at", "达成；到达"),
    ("ascribe...to...", "把…归因于"), ("aspire to", "渴望；追求"), ("attach importance to", "重视"),
    ("attribute...to...", "把…归因于"), ("back up", "支持；备份"), ("base...on...", "以…为基础"),
    ("bear in mind", "记住"), ("benefit from", "从…受益"), ("blame...for...", "因…责备"),
    ("boil down to", "归结为"), ("break down", "分解；崩溃；出故障"), ("break through", "突破"),
    ("break up", "分手；解体"), ("bring about", "引起；导致"), ("bring out", "出版；使显现"),
    ("bring up", "抚养；提出"), ("build up", "增强；积累"), ("burn out", "燃尽；筋疲力尽"),
    ("by contrast", "相比之下"), ("by means of", "借助；通过"), ("by virtue of", "凭借；由于"),
    ("call for", "需要；呼吁"), ("call off", "取消"), ("call on", "号召；拜访"),
    ("capable of", "有能力的"), ("care about", "在乎；关心"), ("carry out", "执行；实施"),
    ("cast doubt on", "使对…产生怀疑"), ("catch up with", "赶上"), ("cater to/for", "迎合；满足"),
    ("come across", "偶然遇到"), ("come along", "进展；一起来"), ("come up with", "想出；提出"),
    ("comment on", "评论"), ("commit oneself to", "致力于"), ("compare...with/to...", "与…比较"),
    ("compensate for", "补偿"), ("complain about", "抱怨"), ("comply with", "遵守"),
    ("be composed of", "由…组成"), ("conceive of", "构想"), ("concentrate on", "集中注意于"),
    ("be concerned about", "关心；担忧"), ("confer with", "协商"), ("confide in", "信任；吐露"),
    ("conform to", "符合；遵照"), ("be confronted with", "面对"), ("consist of", "由…构成"),
    ("consist in", "在于"), ("consult with", "商量"), ("contend with", "应对；搏斗"),
    ("contribute to", "促成；贡献于"), ("cope with", "应付；处理"), ("correspond to/with", "对应；相符"),
    ("count on", "依靠；指望"), ("cover up", "掩盖"), ("crop up", "突然出现"),
    ("cut back on", "削减"), ("cut down on", "减少"), ("cut off", "切断；隔绝"),
    ("deal with", "处理；涉及"), ("dedicate...to...", "把…奉献给"), ("derive from", "源自"),
    ("devote...to...", "把…奉献给"), ("die down", "减弱；平息"), ("die out", "灭绝；消失"),
    ("differ from", "不同于"), ("dispose of", "处理；处置"), ("distinguish...from...", "区分"),
    ("divide...into...", "把…分成"), ("do away with", "废除；去掉"), ("draw on", "利用；动用"),
    ("draw up", "起草；制定"), ("drop out (of)", "退出；辍学"), ("engage in", "从事于"),
    ("be engaged in", "忙于；从事"), ("be entitled to", "有权享有"), ("equip...with...", "配备"),
    ("be essential to", "对…必不可少"), ("excel at/in", "擅长"), ("exclude...from...", "把…排除在外"),
    ("expose...to...", "使暴露于"), ("face up to", "勇敢面对"), ("fall back on", "求助于；退守"),
    ("fall behind", "落后"), ("fall prey to", "成为…的受害者"), ("feed on", "以…为食"),
    ("figure out", "弄明白；解决"), ("fill in/out", "填写"), ("find fault with", "挑剔；批评"),
    ("focus on", "聚焦于"), ("gain access to", "获得进入权；获得"), ("gear...towards/to...", "使适应"),
    ("get across", "使被理解"), ("get along with", "与…相处"), ("get over", "克服；恢复"),
    ("get round to", "腾出时间做"), ("give in (to)", "让步；屈服"), ("give off", "散发；发出"),
    ("give rise to", "引起；导致"), ("give up", "放弃"), ("go about", "着手做；处理"),
    ("go after", "追求"), ("go against", "违背；反对"), ("go along with", "赞同；伴随"),
    ("go beyond", "超出；超越"), ("go in for", "爱好；从事"), ("go through", "经历；仔细检查"),
    ("grow up", "长大"), ("hand down", "传下来；流传"), ("hand in", "上交"),
    ("hand out", "分发"), ("hang on", "坚持；抓紧"), ("hold back", "抑制；阻挡"),
    ("hold on to", "抓住；保持"), ("identify...with...", "把…与…等同"), ("immerse...in...", "使沉浸于"),
    ("impose...on...", "把…强加于"), ("improve on", "改进"), ("inform...of...", "通知"),
    ("insist on", "坚持"), ("interfere with/in", "干涉；妨碍"), ("be involved in", "卷入；参与"),
    ("keep abreast of", "了解…的最新情况"), ("keep an eye on", "留意；照看"), ("keep pace with", "跟上"),
    ("keep track of", "掌握…的线索"), ("knock out", "淘汰；击倒"), ("laugh at", "嘲笑"),
    ("lay off", "解雇"), ("lay out", "布置；设计"), ("lead to", "导致"),
    ("lean on/upon", "依靠"), ("leave alone", "别管；让…独处"), ("leave out", "遗漏；省略"),
    ("let alone", "更不用说"), ("live up to", "不辜负；达到"), ("live with", "忍受；与…同居"),
    ("long for", "渴望"), ("look after", "照顾"), ("look down on/upon", "轻视；看不起"),
    ("look forward to", "期待"), ("look into", "调查"), ("look out for", "留意；提防"),
    ("look up to", "尊敬；敬仰"), ("make out", "辨认出；理解"), ("make up for", "弥补"),
    ("make up", "组成；编造；和解"), ("make the most of", "充分利用"), ("meet with", "遭遇；会晤"),
    ("mistake...for...", "把…误认为"), ("mount up", "增加；上升"), ("move on", "继续前进；转入下一步"),
    ("narrow down", "缩小；收窄"), ("object to", "反对"), ("occur to", "被想到"),
    ("be opposed to", "反对"), ("originate from/in", "起源于"), ("participate in", "参加"),
    ("pass up", "放过；放弃（机会）"), ("pay off", "还清；得到回报"), ("persist in", "坚持"),
    ("pick up", "捡起；学会；接（人）"), ("point out", "指出"), ("pour into", "涌入；注入"),
    ("prepare for", "为…做准备"), ("preside over", "主持"), ("prevail over", "战胜；占优势"),
    ("prevent...from...", "阻止"), ("profit from/by", "从…获利"), ("provide...with...", "提供"),
    ("pull down", "拆毁"), ("pull through", "渡过难关；恢复健康"), ("put across", "表达清楚；使被理解"),
    ("put aside", "储蓄；撇开"), ("put away", "收好；储存"), ("put down to", "把…归因于"),
    ("put forward", "提出（建议/理论）"), ("put off", "推迟"), ("put out", "扑灭；出版"),
    ("put up with", "容忍；忍受"), ("reckon on", "指望；依赖"), ("refer to...as...", "把…称作"),
    ("refrain from", "克制；避免"), ("regard...as...", "把…视为"), ("rely on", "依靠"),
    ("remind...of...", "使想起"), ("resort to", "诉诸；求助于"), ("respond to", "回应"),
    ("be responsible for", "对…负责"), ("restrain...from...", "抑制；阻止"), ("result from", "起因于"),
    ("result in", "导致"), ("ring up", "打电话"), ("rise to", "应对（挑战）"),
    ("rule out", "排除；取消"), ("run into", "偶然遇见；遭遇"), ("run out (of)", "用完；耗尽"),
    ("run over", "碾过；快速过一遍"), ("see through", "看穿；识破"), ("see to it that", "确保；务必使"),
    ("seek after/for", "寻求；追求"), ("send for", "派人去请"), ("set about", "着手；开始"),
    ("set aside", "留出；拨出；不顾"), ("set back", "推迟；阻碍"), ("set out to do", "着手做；打算做"),
    ("set up", "建立；设立"), ("settle for", "将就；勉强接受"), ("settle in", "安顿下来"),
    ("shake off", "摆脱；抖落"), ("share...with...", "与…分享"), ("show off", "炫耀"),
    ("show up", "露面；出现"), ("shut down", "关闭；停业"), ("shut out", "把…排除在外"),
    ("single out", "挑出；选出"), ("sit in on", "旁听；列席"), ("slow down", "减速；放慢"),
    ("sort out", "整理；解决"), ("speak out (against)", "大胆地说；公开反对"), ("specialize in", "专门研究；专营"),
    ("speculate about/on", "推测；投机"), ("stand for", "代表；主张；容忍"), ("stand out", "突出；显眼"),
    ("stem from", "起源于"), ("stick to", "坚持；遵守"), ("be subject to", "易受；服从于"),
    ("submit...to...", "提交；服从"), ("subscribe to", "订阅；赞同"), ("substitute...for...", "用…代替"),
    ("succeed in", "成功做"), ("suffer from", "遭受；患（病）"), ("sum up", "总结；概括"),
    ("supply...with...", "向…供应"), ("take account of", "考虑到"), ("take advantage of", "利用"),
    ("take after", "长相/性格像（长辈）"), ("take apart", "拆开"), ("take...for granted", "认为…理所当然"),
    ("take in", "吸收；欺骗；领会"), ("take into account", "考虑到"), ("take on", "承担；呈现；雇用"),
    ("take over", "接管；接任"), ("take part in", "参加"), ("take pride in", "以…为傲"),
    ("take the place of", "代替"), ("take to", "开始喜欢；养成…习惯"), ("take up", "占据；开始从事"),
    ("tell...from...", "辨别；区分"), ("think highly of", "高度评价"), ("think over", "仔细考虑"),
    ("throw light on", "阐明；使…清楚"), ("tie up with", "与…密切联系"), ("track down", "追查到；找到"),
    ("try on", "试穿"), ("try out", "试用；试验"), ("turn a blind eye to", "对…视而不见"),
    ("turn down", "拒绝；调低"), ("turn out", "结果是；生产； turnout"), ("turn out to be", "结果是；证明是"),
    ("turn to", "求助于；转向"), ("turn up", "出现；调大"), ("up to", "取决于；多达；从事"),
    ("use up", "用完；耗尽"), ("vary from...to...", "因…而异"), ("wait on", "服侍；招待"),
    ("warm up", "热身；预热"), ("watch out for", "提防；密切注意"), ("wear off", "逐渐消失"),
    ("wear out", "磨损；使疲劳"), ("wipe out", "消灭；彻底摧毁"), ("work out", "解决；算出；健身"),
    ("worry about", "担心"), ("write off", "勾销；取消"), ("yield to", "屈服于；让步于"),
    ("a case in point", "恰当的例子"), ("a couple of", "几个；一对"), ("a wide range of", "各种各样的"),
    ("above all", "最重要的是"), ("add up to", "合计达；意味着"), ("all of a sudden", "突然"),
    ("as a result (of)", "由于；因此"), ("as far as...be concerned", "就…而言"), ("as well as", "也；和…一样"),
    ("at the expense of", "以…为代价"), ("at large", "整体上；逍遥法外"), ("at the cost of", "以…为代价"),
    ("be bound to", "必定会"), ("be committed to", "致力于；忠诚于"), ("be concerned with", "涉及；与…有关"),
    ("be familiar with/to", "熟悉；为…所熟知"), ("be fed up with", "厌倦；厌烦"), ("be made up of", "由…组成"),
    ("be short of", "缺乏；不足"), ("be tired of", "厌倦"), ("be used to", "习惯于"),
    ("break away from", "脱离；放弃"), ("break in", "闯入；插嘴"), ("break into", "闯入；突然开始"),
    ("bring...into play", "发挥；使起作用"), ("by accident", "偶然"), ("by and large", "总的来说"),
    ("by chance", "偶然；碰巧"), ("by far", "迄今为止最…；显然"), ("catch one's breath", "喘口气；屏息"),
    ("come into being", "形成；产生"), ("come to terms with", "妥协；接受"), ("come true", "实现"),
    ("cut in", "插嘴；超车"), ("day in and day out", "日复一日"), ("do harm to", "损害；对…有害"),
    ("drop in on", "顺便拜访"), ("every now and then", "不时；偶尔"), ("face to face", "面对面"),
    ("fall in love with", "爱上"), ("far from", "远非；完全不"), ("feel like", "想要；摸起来像"),
    ("few and far between", "稀少；罕见"), ("first and foremost", "首要的是"), ("for fear of", "生怕；以免"),
    ("for good", "永久地"), ("for the sake of", "为了…起见"), ("get by", "过得去；勉强应付"),
    ("get down to", "开始认真做"), ("give way to", "让步于；被…取代"), ("go wrong", "出错；出故障"),
    ("had better", "最好"), ("hand over", "移交；交出"), ("have access to", "可以使用；能接触到"),
    ("have an impact on", "对…有影响"), ("have difficulty (in) doing", "做…有困难"), ("hold on", "坚持住；等一等"),
    ("if only", "要是…就好了"), ("in accordance with", "依照；与…一致"), ("in addition to", "除…之外还"),
    ("in advance", "提前；预先"), ("in agreement with", "同意；与…一致"), ("in any case/event", "无论如何"),
    ("in brief/short", "简言之"), ("in case of", "万一；如果发生"), ("in charge of", "负责；主管"),
    ("in common", "共同（的）"), ("in contrast to/with", "与…形成对比"), ("in danger of", "处于…的危险中"),
    ("in debt", "负债"), ("in demand", "有需求的；吃香的"), ("in depth", "深入地；彻底地"),
    ("in detail", "详细地"), ("in effect", "实际上；生效"), ("in essence", "本质上"),
    ("in favor of", "支持；赞成"), ("in general", "总的来说"), ("in honor of", "为了纪念；向…致敬"),
    ("in no time", "立刻；很快"), ("in other words", "换句话说"), ("in particular", "尤其；特别"),
    ("in person", "亲自"), ("in practice", "实际上；在实践中"), ("in return for", "作为…的回报"),
    ("in short supply", "供应不足"), ("in spite of", "尽管"), ("in terms of", "就…而言；在…方面"),
    ("in the long run", "从长远来看"), ("in the course of", "在…期间"), ("in the face of", "面对；不顾"),
    ("in touch with", "与…保持联系"), ("in vain", "徒劳；白费"), ("keep in touch with", "与…保持联系"),
    ("keep off", "避开；不接近"), ("keep up with", "跟上；保持联系"), ("kill two birds with one stone", "一石二鸟"),
    ("let go of", "放开；释放"), ("little by little", "一点一点地；逐渐"), ("look on", "旁观；看待"),
    ("make a difference", "有影响；起作用"), ("make friends with", "与…交朋友"), ("make fun of", "取笑；嘲弄"),
    ("make progress", "取得进步"), ("make sense", "有意义；讲得通"), ("make sure", "确保"),
    ("make up one's mind", "下决心"), ("more often than not", "往往；多半"), ("neither...nor...", "既不…也不…"),
    ("no matter how/what", "无论怎样/什么"), ("no sooner...than...", "一…就…"), ("not to mention", "更不用说"),
    ("now that", "既然"), ("on behalf of", "代表"), ("on purpose", "故意地"),
    ("on the contrary", "相反"), ("on the grounds of", "基于…的理由"), ("on the spot", "当场；在现场"),
    ("once and for all", "一劳永逸地"), ("one after another", "一个接一个"), ("or else", "否则；要不然"),
    ("other than", "除了；不同于"), ("out of order", "出故障；秩序混乱"), ("out of the question", "不可能"),
    ("over and over again", "反复地；一再"), ("owing to", "由于"), ("prior to", "在…之前"),
    ("provide for", "供养；为…做准备"), ("regardless of", "不管；不顾"), ("right away", "立刻；马上"),
    ("so as to", "以便；为了"), ("so...that...", "如此…以至于"), ("sooner or later", "迟早"),
    ("thanks to", "多亏；由于"), ("that is (to say)", "也就是说"), ("the moment (that)", "一…就…"),
    ("to begin with", "首先；一开始"), ("to some extent", "在某种程度上"), ("under control", "处于控制之下"),
    ("under no circumstances", "决不"), ("under way", "进行中"), ("up to date", "最新的；现代的"),
    ("used to do", "过去常常做"), ("wait for", "等待"), ("walk out (on)", "突然离开；遗弃"),
    ("what if", "如果…会怎样"), ("whether or not", "是否；无论是否"), ("with respect to", "关于；就…而言"),
    ("with the exception of", "除…之外"), ("would rather", "宁愿"),
]

MULTIWORD_MAX = 5  # 词组最多单词数


def clean_translation(t: str) -> str:
    t = t.replace("\n", "；").strip()
    t = t.replace("[网络]", "").strip()
    return t


def main():
    if not os.path.exists(CSV_PATH):
        print("未找到 ecdict.csv，请先下载 ECDICT")
        sys.exit(1)

    words_cet6, words_ky, phrases = [], [], []
    seen_cet6, seen_ky, seen_phrase = set(), set(), set()

    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            w = (row.get("word") or "").strip().lower()
            if not w or " " not in w and not w.replace("-", "").replace("'", "").isalnum():
                pass
            tags = (row.get("tag") or "").lower()
            translation = clean_translation(row.get("translation") or "")
            definition = (row.get("definition") or "").strip()
            try:
                frq = int(row.get("frq") or 0)
            except ValueError:
                frq = 0
            phonetic = (row.get("phonetic") or "").strip().strip(",")

            if " " in w or "  " in w.strip():
                # 短语词条
                n_words = len(w.split())
                if 2 <= n_words <= MULTIWORD_MAX and translation and (frq > 0 or "cet" in tags or "ky" in tags):
                    key = re.sub(r"[^a-z ]", "", w).strip()
                    if key and key not in seen_phrase and not key.startswith(("sb ", "sth ")):
                        seen_phrase.add(key)
                        phrases.append({"text": key, "translation": translation,
                                        "note": definition[:200] if definition else ""})
                continue
            if not w or not translation:
                continue
            item = {"headword": w, "phonetic_us": phonetic, "translation": translation,
                    "definition": definition[:500], "tags": tags, "freq": frq}
            if "cet6" in tags and w not in seen_cet6:
                seen_cet6.add(w)
                words_cet6.append(item)
            if " ky" in f" {tags} " and w not in seen_ky:
                seen_ky.add(w)
                words_ky.append(item)

    for text, trans in CORE_PHRASES:
        if text not in seen_phrase:
            seen_phrase.add(text)
            phrases.insert(0, {"text": text, "translation": trans, "note": "core"})

    words_cet6.sort(key=lambda x: -x["freq"])
    words_ky.sort(key=lambda x: -x["freq"])
    phrases.sort(key=lambda p: 0 if p.get("note") == "core" else 1)

    with open(os.path.join(OUT_DIR, "words.json"), "w", encoding="utf-8") as f:
        json.dump({"cet6": words_cet6, "kaoyan": words_ky}, f, ensure_ascii=False)
    with open(os.path.join(OUT_DIR, "phrases.json"), "w", encoding="utf-8") as f:
        json.dump(phrases, f, ensure_ascii=False)

    print(f"六级词书: {len(words_cet6)} 词")
    print(f"考研词书: {len(words_ky)} 词")
    print(f"短语书: {len(phrases)} 条")


if __name__ == "__main__":
    main()
