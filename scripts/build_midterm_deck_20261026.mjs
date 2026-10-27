// 在 Artifact Session 回调中调用，保持画布与交付 PPT 使用同一份内容。
import fs from 'node:fs/promises';
import path from 'node:path';
const FONT='Noto Sans CJK SC', MONO='Noto Sans Mono CJK SC';
const C={ink:'#102D3B',paper:'#F7F6F1',muted:'#54666F',line:'#D5DEDE',teal:'#16876E',mint:'#8ADBC7',red:'#BB493F',paleRed:'#F6E7E2',paleGreen:'#E5F1EB',blue:'#527A99',gold:'#D6AE64',white:'#FFFFFF'};
export async function build(pres,root){
 const data=JSON.parse(await fs.readFile(path.join(root,'build/midterm-20261026/content.json'),'utf8'));
 pres.slides.keep([]);pres.theme.defaultFont=FONT;
 const text=(s,v,x,y,w,h,size=28,color=C.ink,bold=false,font=FONT)=>{
  const t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  t.text=v;t.text.insets=0;t.text.style={typeface:font,fontSize:size,bold,color};return t;
 };
 const box=(s,x,y,w,h,fill,line='none',geometry='rect')=>s.shapes.add({geometry,position:{left:x,top:y,width:w,height:h},fill,line:{fill:line,width:line==='none'?0:1}});
 const arrow=(s,x,y,w=34,color=C.teal)=>box(s,x,y,w,20,color,'none','rightArrow');
 function footer(s,i,dark=false){const col=dark?'#B8CFD2':C.muted;box(s,54,660,1172,1,dark?'#35525E':C.line);text(s,'大创中期汇报  ·  2026.10',54,677,500,24,16,col);text(s,`${i+1} / 7`,1170,674,65,28,18,col);}
 function heading(s,t,dark=false){text(s,t,54,46,1172,72,43,dark?C.white:C.ink,true);}
 function table(s,values,x,y,w,h,widths,size=23){
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});
  t.borders.assign({fill:C.line,width:1,style:'solid'});
  for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){const cell=t.getCell(r,c);cell.fill=r===0?C.ink:(r%2?C.white:'#EFF3EF');cell.text.style={typeface:FONT,fontSize:size,bold:r===0,color:r===0?C.white:C.ink};}
  return t;
 }
 const sources=[
  '项目开题报告（私有原件）；中期报告20261026。',
  'safety_harness/security_probe.py及项目测试；程序分析与动态证据分开统计。',
  'safety_harness/源码；docs/客户端使用.md；https://bandit.readthedocs.io/；https://github.com/deepseek-ai/deepseek-harness。方法背景：https://arxiv.org/abs/2403.16218；https://arxiv.org/abs/2412.14137。',
  'results/reference/summary.json；deliverables/演示回放.mp4。人工参考测试真实记录回放，不是模型实验；视频独立文件，未嵌入。',
  'results/frozen-20261022/analysis.json；results/benchmark-20261025/analysis.json。24人工评测样本有模板相关性；冻结主要比较排除3超预算匹配块，该规则非原始预注册；全量A62/72、B63/72、C68/72。两批分开报告。',
  'results/private/client/validation-20261025.json；.impeccable/review/desktop.png；用户提供12份审查反馈尚缺完整动态与真人复核证据。',
  '研究计划，尚未完成的工作。来源、数据划分、成本与消融需先确定再开展。',
 ];
 for(let i=0;i<7;i++){
  const s=pres.slides.add();const dark=[0,2].includes(i);s.background.fill=dark?C.ink:C.paper;
  footer(s,i,dark);
  if(i===0){
   text(s,'基于程序分析的代码智能体',54,92,1160,72,49,C.white,true);
   text(s,'安全性测试 Harness 构建方法',54,170,1160,76,49,C.white,true);
   text(s,'相同模型与调用预算下，\n风险上下文能否帮助模型\n生成更有效的安全测试？',58,303,660,174,36,C.white);
   text(s,'路径穿越   /   命令注入   /   SQL 注入',58,560,710,46,25,C.mint);
   box(s,805,300,417,291,'#193B49','#42616D');
   text(s,'同一安全性质测试',830,322,368,44,26,C.mint,true);
   box(s,830,381,365,1,'#49606A');
   text(s,'缺陷版',830,408,150,37,25,C.white);
   text(s,'违规',1075,406,100,41,30,'#F3A69A',true);
   text(s,'修复版',830,472,150,37,25,C.white);
   text(s,'通过',1075,470,100,41,30,C.mint,true);
   text(s,'保留输入、日志与哈希',830,541,350,31,20,'#BDCFD2');
  }
  if(i===1){
   heading(s,data.slides[i].title);
   text(s,'静态告警提供线索，动态执行确认实际违规',56,133,1160,50,29,C.muted);
   const rows=[['路径穿越','文件访问越过指定目录','目录外随机哨兵'],['命令注入','输入改变命令执行行为','无害执行标记'],['SQL 注入','输入改变查询的授权范围','越权 PRIVATE 行']];
   text(s,'本阶段范围',65,215,250,34,22,C.muted);text(s,'需要验证的行为',380,215,480,34,22,C.muted);text(s,'有效证据',930,215,280,34,22,C.muted);
   rows.forEach((r,j)=>{const y=266+j*94;box(s,55,y-8,1170,1,C.line);text(s,r[0],65,y+8,300,50,32,C.ink,true);text(s,r[1],380,y+10,520,50,27);text(s,r[2],930,y+10,280,50,25,C.teal,true);});
   box(s,54,568,1172,67,'#E6ECE8');text(s,'延期内容：符号执行、自动修复、跨语言与完整项目分析',78,585,1120,40,25);
  }
  if(i===2){
   heading(s,data.slides[i].title,true);
   text(s,'代码进入，证据输出；失败反馈仅用于修订测试',56,130,1160,48,29,'#BDD0D3');
   const nodes=[['Python 代码','源码与需求','统一测试规范'],['风险上下文','Bandit 告警','AST 函数与导入'],['生成测试','受限 pytest','Hypothesis 输入'],['隔离执行','无网络容器','probe 安全判据'],['证据汇总','缺陷／修复配对','日志与哈希']];
   nodes.forEach((r,j)=>{let x=54+j*239;box(s,x,246,214,186,j===3?'#255A59':'#1D4050',j===3?C.mint:'#51717E');text(s,r[0],x+15,267,188,48,29,C.white,true);text(s,r[1],x+15,335,188,40,22,j===3?C.mint:'#CADBDD');text(s,r[2],x+15,375,188,40,22,'#CADBDD');if(j<4)arrow(s,x+219,326,16,C.mint);});
   // 反馈箭头回到生成测试，目标代码不随反馈修改。
   box(s,639,437,1,42,C.mint);box(s,639,478,240,2,C.mint);box(s,878,436,2,44,C.mint);
   box(s,629,433,20,20,C.mint,'none','upArrow');
   text(s,'缺陷版反馈 → 最多修订两次，仅修改测试',536,492,659,43,23,C.mint);
   text(s,'复用',58,574,88,36,24,'#B6C9CF',true);text(s,'Bandit / pytest / Hypothesis / 容器',150,574,480,36,23,C.white);
   text(s,'自主实现',664,574,154,36,24,C.mint,true);text(s,'上下文、判据、编排与证据',823,574,405,36,23,C.white);
  }
  if(i===3){
   heading(s,data.slides[i].title);
   box(s,54,143,1172,60,C.ink);text(s,'输入：../secret.txt',78,155,700,43,28,C.white,true,MONO);text(s,'path-01 · 人工参考测试',866,160,340,36,22,C.mint);
   box(s,54,229,567,340,C.paleRed);box(s,659,229,567,340,C.paleGreen);
   text(s,'缺陷版',82,251,480,51,35,C.red,true);text(s,'修复版',687,251,480,51,35,C.teal,true);
   text(s,'open(join(root, value))',82,324,510,58,25,C.ink,false,MONO);
   text(s,'resolve + boundary check',687,324,510,58,25,C.ink,false,MONO);
   text(s,'读到目录外的随机哨兵',82,403,510,52,30,C.ink,true);text(s,'拒绝越界访问',687,403,510,52,30,C.ink,true);
   text(s,'violation · 违规',82,492,510,52,31,C.red,true);text(s,'pass · 同一测试通过',687,492,510,52,31,C.teal,true);
   text(s,'20 秒真实记录回放',55,596,400,41,27,C.ink,true);text(s,'验证执行链路；模型效果由对照实验判断',495,598,730,40,25,C.muted);
  }
  if(i===4){
   heading(s,'冻结批次 C 较高，补充试跑 B 与 C 持平');
   text(s,'A 源码直接生成     B 增加 Bandit 告警     C 再增加 AST 上下文',56,129,1170,44,25,C.muted);
   const chart=s.charts.add('bar',{
    position:{left:48,top:199,width:620,height:346},title:'配对复现率',titleTextStyle:{fontSize:24,fill:C.ink,bold:true},
    categories:['冻结主要比较','补充试跑'],
    series:['A','B','C'].map((g,k)=>({name:g,values:[data.frozen[k].confirmed_rate,data.supplement[k].confirmed_rate],fill:[C.blue,C.gold,C.teal][k],valuesFormatCode:'0.0%'})),
    hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:20,fill:C.ink}},
    barOptions:{direction:'column',grouping:'clustered',gapWidth:90},
    xAxis:{textStyle:{fontSize:20,fill:C.ink},line:{fill:C.line,width:1}},
    yAxis:{min:0,max:1,majorUnit:.25,numberFormatCode:'0%',textStyle:{fontSize:17,fill:C.muted},majorGridlines:{fill:C.line,width:1}},
    dataLabels:{visible:true,showValue:true,position:'outEnd',numberFormatCode:'0.0%',textStyle:{fontSize:18,fill:C.ink}},
    chartFill:C.paper,plotAreaFill:C.paper,chartLine:{fill:'none',width:0},
   });
   const {applyPresentationChartFont}=await import('/home/takina/.codex/plugins/cache/openai-primary-runtime/presentations/26.1024.11018/skills/presentations/container_tools/artifact_tool_utils.mjs');
   applyPresentationChartFont(chart,{fontFamily:FONT});
   table(s,[['批次','A','B','C'],['冻结主要','61/69','62/69','67/69'],['补充试跑','20/24','22/24','22/24']],701,224,523,163,[169,118,118,118],22);
   text(s,'原始 216 次；主要比较 207 次',705,413,520,40,23,C.ink,true);
   text(s,'7 次不确定请求计入调用上限\n排除 3 个超预算 A/B/C 匹配块',705,459,520,75,22,C.muted);
   box(s,54,568,1172,70,'#ECE6D9');text(s,'失败案例  path-10',76,588,309,36,25,C.ink,true);text(s,'三组某轮均漏掉 ./../secret.txt；未触发 ≠ 安全',390,589,814,39,24,C.ink);
  }
  if(i===5){
   heading(s,data.slides[i].title);
   s.images.add({path:path.join(root,'.impeccable/review/desktop.png'),alt:'2026年10月25日真实客户端截图：会话、工具过程和已拒绝的修改提案',fit:'contain',position:{left:54,top:151,width:730,height:456}});
   box(s,866,151,1,438,C.line);
   text(s,'已验证的操作',891,154,337,42,29,C.teal,true);
   text(s,'读代码 · 静态分析\n已知案例隔离配对\n修改差异与审批',891,210,337,125,25);
   text(s,'当前待补',891,359,337,42,29,C.red,true);
   text(s,'12 份真实输出动态验收\n两人独立标签\n两轮真人计时',891,413,337,125,24);
   text(s,'项目自有 Agent + DeepSeek API',891,566,337,38,18,C.muted);
   text(s,'负责人：方法与集成   ·   动态：隔离与案例   ·   数据：标签与材料',57,618,1160,36,22,C.muted);
  }
  if(i===6){
   heading(s,'下一步研究更真实的代码与更有效的上下文');
   const stages=[['1—2 周','真实样本与可靠标签','独立来源、正常功能 + 安全性质、双人复核'],['3—5 周','更有用的局部上下文','输入到敏感调用的依赖、多函数代码、去依赖消融'],['6—8 周','检验增益及成本','强基线、去反馈、第二模型、每次成功成本']];
   stages.forEach((r,j)=>{const y=181+j*120;box(s,70,y+24,14,14,j===0?C.teal:C.blue,'none','ellipse');if(j<2)box(s,76,y+41,2,101,C.line);text(s,r[0],110,y+7,185,45,29,C.teal,true);text(s,r[1],330,y,875,47,33,C.ink,true);text(s,r[2],330,y+55,875,44,25,C.muted);});
   box(s,54,572,1172,66,C.ink);text(s,'符号执行：当失败分析证明路径约束是主要障碍时，再做有界试验',79,590,1120,40,25,C.white);
  }
  s.speakerNotes.text=data.slides[i].speech+'\n\n页预算：'+data.slides[i].time+'秒。'+(i===3?'含20秒独立视频回放。':'')+'\n\n来源与口径：'+sources[i];
 }
 return {slides:pres.slides.items.length,font:FONT,scriptCharacters:data.chinese_characters};
}
