import {chromium} from 'playwright';
import fs from 'node:fs/promises';
const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
const context=await browser.newContext({viewport:{width:1280,height:720},recordVideo:{dir:'build/video',size:{width:1280,height:720}}});
const page=await context.newPage();await page.goto('file://'+process.cwd()+'/deliverables/演示.html#record');await page.evaluate(()=>document.fonts.ready);await page.evaluate(()=>play());await page.waitForTimeout(20200);await page.screenshot({path:'build/video-final.png'});const video=page.video();await context.close();await video.saveAs('build/replay.webm');await browser.close();
console.log('Recorded evidence replay');
