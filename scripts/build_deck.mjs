import fs from 'node:fs/promises';
import path from 'node:path';
import {Presentation,PresentationFile} from '@oai/artifact-tool';
import {pathToFileURL} from 'node:url';
const root=process.cwd(), skill=process.env.PRESENTATION_SKILL_DIR;
if (!skill || !process.env.RUNTIME_PYTHON) throw new Error('Set PRESENTATION_SKILL_DIR and RUNTIME_PYTHON to the installed artifact runtime.');
const {finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')).href);
const data=JSON.parse(await fs.readFile('scripts/presentation_content.json','utf8'));
const pres=Presentation.create({slideSize:{width:1280,height:720}});
const font='WenQuanYi Zen Hei';
pres.theme.defaultFont=font;
function text(s,value,x,y,w,h,size=30,bold=false,color='#191919'){
 let t=s.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 t.text=value;t.text.style={typeface:font,fontSize:size,bold,color};return t;
}
for(let i=0;i<7;i++){
 const s=pres.slides.add();s.background.fill='#FAFAF7';
 text(s,String(i+1).padStart(2,'0')+' / 07',1130,652,100,30,20,false,'#777777');
 text(s,data[i].title,64,i===0?128:55,1150,i===0?170:82,i===0?53:46,true);
 if(i===0){text(s,data[i].body[0],68,65,1100,45,25,false,'#555555');text(s,data[i].body[1],68,365,1120,150,36);text(s,'中期研究范围：路径穿越 · 命令注入 · SQL 注入',68,595,1070,42,24,false,'#555555');}
 if(i===1){for(let j=0;j<3;j++)text(s,data[i].body[j],68,210+j*135,1120,j===2?120:80,34);}
 if(i===2){for(let j=0;j<4;j++)text(s,data[i].body[j],68,177+j*95,1120,70,32);text(s,'自主实现：上下文组织、可信探针、隔离证据与对照实验',68,593,1100,50,25,true);}
 if(i===3){
 text(s,'输入  ../secret.txt',68,155,1100,64,36,true);
 text(s,'缺陷版',68,260,500,50,32,true);text(s,'open(join(root, value))',68,325,540,55,28);text(s,'返回目录外哨兵内容\n判定：violation',68,425,530,110,32);
 text(s,'修复版',690,260,500,50,32,true);text(s,'resolve + is_relative_to',690,325,520,55,28);text(s,'拒绝越界路径\n判定：pass',690,425,500,110,32);
 text(s,'播放配套 20 秒录像：人工参考测试的真实记录回放',68,590,1090,45,25,false,'#555555');
 }
 if(i===4){
 text(s,'30 / 30',64,150,400,105,78,true);text(s,'人工参考配对成立\n修复版触发 0 / 30',500,170,650,90,30);
 let rows=[['A 直接生成','需求、代码、统一测试规范'],['B 告警引导','A + Bandit 告警'],['C 上下文引导','B + AST 风险函数与依赖']];
 let table=s.tables.add({rows:3,columns:2,left:68,top:298,width:1140,height:188,columnWidths:[290,850],values:rows});
 table.borders.assign({fill:'#D7D7D7',width:1,style:'solid'});
 for(let r=0;r<3;r++)for(let c=0;c<2;c++){const cell=table.getCell(r,c);cell.fill='#FAFAF7';cell.text.style={typeface:font,fontSize:27,bold:c===0,color:'#191919'};}
 text(s,'24 样本 × 3 组 × 3 重复；每次最多 3 次调用',68,510,1135,44,28);
 text(s,'模型实验尚未运行。断言错误与超时不计漏洞。',68,570,1135,46,28,true);
 }
 if(i===5){text(s,data[i].body[0],68,173,1135,85,32,true);text(s,data[i].body[1],68,295,1135,130,31);text(s,data[i].body[2],68,460,1135,130,31,false,'#555555');}
 if(i===6){for(let j=0;j<4;j++)text(s,data[i].body[j],68,180+j*105,1135,80,32,j===0);}
 s.speakerNotes.text=data[i].speech+'\n\n页预算：'+data[i].time+'秒。'+(i===3?'播放同目录“演示回放.mp4”，20秒静音。':'')+'\n资料：项目开题报告；results/reference/summary.json；results/server/；results/unit-tests.xml；results/container-tests.xml。\n工具资料：https://bandit.readthedocs.io/en/latest/ ；https://github.com/deepseek-ai/deepseek-harness 。当前无真实模型A/B/C结果。';
}
await fs.mkdir('build/slides',{recursive:true});
for(let i=0;i<7;i++)await fs.writeFile(`build/slides/slide-${i+1}.png`,new Uint8Array(await (await pres.export({slide:pres.slides.items[i],format:'png',scale:1})).arrayBuffer()));
await (await PresentationFile.exportPptx(pres)).save('build/candidate.pptx');
const result=await finalizePresentation({workspaceDir:root,candidatePath:path.join(root,'build/candidate.pptx'),finalPath:path.join(root,'deliverables/五分钟答辩.pptx'),pythonExecutable:process.env.RUNTIME_PYTHON,integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-bullet-geometry','--validate-heading-fit','--require-native-table-slide','5'],explicitTotalSlideCount:7,requiredNativeTableOwnerSlides:[5],fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,receiptPath:path.join(root,'build/deck-validation.json')});
console.log(JSON.stringify(result));
