"""在 ppt-master 原生往返工作区内优化文字、位置和 benchmark 表。"""
from pathlib import Path
import json, re, shutil
import xml.etree.ElementTree as E
ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'build/midterm-20261027/ppt-master-portable'
OUT=ROOT/'deliverables/中期答辩-20261027'
S='http://www.w3.org/2000/svg'; X='http://www.w3.org/XML/1998/namespace'
E.register_namespace('',S)
ns={'s':S}
shutil.copyfile(ROOT/'.impeccable/review/desktop.png',W/'images/client-desktop.jpeg')
def tag(t):return '{'+S+'}'+t

def get(root,id):return next(e for e in root if e.get('id')==id)
def replace(root,id,value):
    t=get(root,id).find('.//s:text',ns)
    for e in list(t):t.remove(e)
    for a in ['data-pptx-text-model','data-paragraph-line-height']:t.attrib.pop(a,None)
    t.text=value

def label(root,id,x,y,w,h,lines,size=22,color='#102D3B',bold=False):
    g=E.SubElement(root,tag('g'),{'id':id,'data-pptx-bounds':f'{x} {y} {w} {h}'})
    for j,v in enumerate(lines):
        a={'x':str(x),'y':str(y+size+j*(size+8)),'font-size':str(size),'fill':color,'font-family':'Noto Sans CJK SC'}
        if bold:a['font-weight']='bold'
        E.SubElement(g,tag('text'),a).text=v
    return g

def rect(root,x,y,w,h,fill):
    return E.SubElement(root,tag('rect'),dict(x=str(x),y=str(y),width=str(w),height=str(h),fill=fill))

# 沿用已确认的七页顺序；每页只修改确认范围内的文字与布局。
plan={'source':'build/midterm-20261027/source-rounded-relative.pptx','confirmed_by':'2026-10-27 用户确认其余方案，取消20秒视频',
 'page_count':7,'seconds':300,'video':False,'narration':False,'animation':False,
 'pages':[{'page':i,'source_slide':i,'status':'edited' if i!=1 else 'referenced','reason':r} for i,r in enumerate([
 '保留题目与研究问题，更新讲稿','调整中期范围标题','缩短长行，保留流程与反馈箭头','删除播放指示，直接讲解配对证据','保留动态图，增加外部静态对比表和分母','修正截图与分工文字的间距','研究计划改为自然、准确的措辞'],1)],
 'sources':['results/frozen-20261022/analysis.json','results/benchmark-20261025/analysis.json','results/benchmark-20261025/securityeval-static.json','results/private/client/validation-20261025.json']}
(W/'validation/confirmed-edit-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
for i in range(2,8):
    p=W/f'authoring-svg-flat/slide_{i:02}.svg';root=E.parse(p).getroot()
    if i==2:replace(root,'shape-5','中期测试范围与判定依据')
    if i==3:
        replace(root,'shape-6','根据风险上下文生成测试，用执行反馈修订输入')
        replace(root,'shape-30','日志与哈希')
    if i==4:
        replace(root,'shape-19','判定依据：实际越界访问')
        replace(root,'shape-20','同一测试在缺陷版违规，在修复版通过')
    if i==5:
        replace(root,'shape-5','Benchmark：动态复现与静态线索')
        # 图表代理保持不动，保留原生数据和百分比刻度。
        for id in ['shape-9','shape-10','shape-11','shape-12','shape-13','static-title','static-limits','dynamic-denominators','budget-note','failed-case']:
            for el in list(root):
                if el.get('id')==id:root.remove(el)
        label(root,'static-title',701,186,523,38,['SecurityEval · 121 份代码'],27,bold=True)
        g=get(root,'shape-8')
        for child in list(g):g.remove(child)
        g.set('data-pptx-frame','701 238 523 190')
        values=[['静态方法','有线索样本','覆盖比例'],['Bandit','48 / 121','39.7%'],['AST','18 / 121','14.9%'],['合并线索','53 / 121','43.8%']]
        widths=[217,158,148];heights=[47.5]*4
        rows=[]
        for r,row in enumerate(values):
            rr=[]
            for col,v in enumerate(row):
                rr.append({'text':v,'fill':'#102D3B' if r==0 else ('#FFFFFF' if r%2 else '#EFF3EF'),'color':'#FFFFFF' if r==0 else '#102D3B','bold':r==0,'font_size':22,'align':'l' if col==0 else 'ctr','valign':'middle','padding':8,'borders':{edge:{'style':'solid','color':'#D5DEDE','width':1} for edge in ['left','right','top','bottom']}})
            rows.append(rr)
        meta={'schema':'ppt-master.semantic-table.v2','x':701,'y':238,'width':523,'height':190,'name':'securityeval-static','column_widths':widths,'row_heights':heights,'defaults':{'run':{'font_family':'Noto Sans CJK SC'}},'rows':rows}
        E.SubElement(g,tag('metadata'),{'type':'application/json'}).text=json.dumps(meta,ensure_ascii=False)
        for r,row in enumerate(values):
            x=701
            for col,v in enumerate(row):
                rect(g,x,238+r*47.5,widths[col],47.5,'#102D3B' if r==0 else ('#FFFFFF' if r%2 else '#EFF3EF'))
                E.SubElement(g,tag('text'),{'x':str(x+12),'y':str(270+r*47.5),'font-size':'22','fill':'#FFFFFF' if r==0 else '#102D3B','font-weight':'bold' if r==0 else 'normal'}).text=v
                x+=widths[col]
        label(root,'static-limits',705,448,520,100,['0 次动态执行；这里只统计静态线索','暂未与主流 Harness 同条件对跑'],22,'#54666F')
        label(root,'dynamic-denominators',59,548,623,62,['冻结 A 61/69 · B 62/69 · C 67/69','补充 A 20/24 · B 22/24 · C 22/24'],21)
        label(root,'budget-note',705,537,520,65,['冻结批次排除 3 个超预算匹配块','两类指标及两批数据分别报告'],21,'#54666F')
        g=E.SubElement(root,tag('g'),{'id':'failed-case','data-pptx-bounds':'54 613 1172 40'})
        rect(g,54,613,1172,40,'#ECE6D9')
        E.SubElement(g,tag('text'),{'x':'76','y':'640','font-size':'22','fill':'#102D3B'}).text='失败案例 path-10：三组某轮均漏掉 ./../secret.txt；未触发不代表安全'
    if i==6:
        replace(root,'shape-5','客户端已运行，真实样本验收仍待完成')
        # 图片是普通嵌入图像，调整原生画框，避免遮挡分工文字。
        for g in root:
            if g.get('data-pptx-object')=='picture':
                for im in g.findall('.//s:image',ns):
                    if im.get('data-pptx-source-proxy'):continue
                    im.set('width','730');im.set('height','456')
                    im.attrib.pop('{http://www.w3.org/1999/xlink}href',None)
                    im.set('href','../images/client-desktop.jpeg')
                g.set('data-pptx-frame','54 151 730 456')
    if i==7:
        replace(root,'shape-5','后续研究计划')
        replace(root,'shape-8','1至2 周');replace(root,'shape-13','3至5 周');replace(root,'shape-17','6至8 周')
        replace(root,'shape-14','风险相关的局部上下文')
    E.ElementTree(root).write(p,encoding='unicode')

speeches=[
'各位老师好，我们的项目是基于程序分析的代码智能体安全性测试Harness构建方法。中期研究的问题是：在相同模型和调用上限下，提供风险位置和函数上下文，能否帮助模型生成更有效的Python安全测试？',
'项目进度落后于开题安排，本阶段收敛到路径穿越、命令注入和SQL注入。静态工具先定位可疑位置，再通过执行检查是否发生违规。例如路径穿越需要读到指定目录外的内容，普通异常不能作为漏洞证据。目前已实现局部分析和动态验证，符号执行、自动修复与跨语言留到后续。',
'程序读取代码后，用Bandit扫描告警，再通过AST整理风险函数、签名和导入。模型据此生成测试输入，在无网络、非特权容器中执行。统一探针准备临时文件或数据库，检查实际违规。未触发时，将缺陷版反馈交给模型，最多修订两次，只修改测试。最终保存日志和哈希并生成统计。自主实现主要包括上下文组织、配对判定、受控执行及证据记录；正式实验直接调用API，官方Harness SDK已完成初始化和MCP启动验证。',
'以路径穿越样本为例，人工参考测试输入点点斜杠secret.txt。缺陷版直接拼接路径，读取到公共目录外的随机哨兵，记录为违规。修复版规范化路径并检查边界，拒绝这次访问，同一测试通过。两次执行使用相同测试，因此可以核对修复前后的差异。这里验证的是执行和判定流程，模型生成测试的效果由对照实验评估。正常功能还需单独检查，避免把拒绝全部输入的实现判为合格。',
'动态评测分三组：A直接给源码，B增加告警，C再增加上下文。冻结评测共216次，计入网络失败并剔除三个超预算匹配块后，每组保留69次，分别复现61、62和67次。补充试跑为20、22和22次，分母均为24，B与C持平。右侧是SecurityEval静态诊断，121份代码中53份有任一线索，尚未执行目标代码。两种指标分别报告，也不能据此与主流Harness排名。失败案例中，三组某轮均遗漏了路径前缀绕过。现有结果限于人工模板和单一模型。试验次数包含重复运行，评测对象仍是二十四个程序，且存在相似模板，结论需要在更多来源验证。',
'客户端已支持通过对话读代码、查看分析结果、运行已知案例，并展示修改差异供用户审批。真实模型调用和路径穿越配对已经验证，当前采用项目自有Agent。负责人承担方法、集成与主讲，另外两位分别负责动态测试和数据材料。十二份真实生成代码已保留，动态验收和双人真人标签仍需完成；AI初审仅作为辅助。',
'下一阶段先完成真实输出的功能验收、安全测试和双人复核，再引入独立来源样本，研究输入到敏感调用的局部依赖。通过去依赖、去反馈和第二模型对照，分析上下文在哪些情况下有效，并比较每次成功的成本。若失败分析表明路径约束是主要障碍，再开展有界符号执行试验。谢谢各位老师。'
]
chars=len(re.findall(r'[\u4e00-\u9fff]',''.join(speeches)))
assert 900<=chars<=1100,chars
for i,t in enumerate(speeches,1):(W/f'notes/slide_{i:02}.md').write_text(t+'\n')
times=[25,35,55,45,75,35,30]
short=['研究问题','测试范围','技术路线','配对案例','Benchmark对比','进展与分工','后续研究']
lines=['# 五分钟逐页讲稿',f'7页，共300秒。正文{chars}个汉字，不含视频；真人彩排目标4分40秒至4分50秒。','']
for i,(t,time,name) in enumerate(zip(speeches,times,short),1):lines += [f'## 第{i}页 {name} {time}秒','',t,'']
(OUT/'逐页讲稿.md').write_text('\n'.join(lines))
(ROOT/'build/midterm-20261027/speeches.json').write_text(json.dumps({'speeches':speeches,'seconds':times,'chinese_characters':chars},ensure_ascii=False,indent=2))
print({'speech_characters':chars,'slides':7,'video':False})
