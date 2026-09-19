import assert from 'node:assert/strict';
import {fitScale} from '../app/static/label-preview.mjs';
for(const [pw,ph,w,h] of [[155.906,42.5197,500,270],[155.906,42.5197,1400,120],[35,35,500,260]]){
 const scale=fitScale(pw,ph,w,h),dw=pw*scale,dh=ph*scale;
 assert(dw<=w-24+1e-6 && dh<=h-24+1e-6);
 assert(Math.min(Math.abs(dw-w+24),Math.abs(dh-h+24))<1e-6);
}
console.log('Fit-to-viewer checks passed');
