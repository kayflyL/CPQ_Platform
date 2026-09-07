const fs=require('fs');
const src=fs.readFileSync('openPlan3D-main/src/lib/components/editor/FloorPlanCanvas.svelte','utf8');
const m=src.match(/<script[\s\S]*?<\/script>/);
const script=m[0];
const state=[];const derived=[];const effect=[];
for(const l of script.split(/\r?\n/)){
  let r;
  r=l.match(/^\s*let\s+([A-Za-z_$][\w$]*)[^=;]*=\s*\$state\b/);
  if(r){state.push(r[1]);continue;}
  r=l.match(/^\s*let\s+([A-Za-z_$][\w$]*)[^=;]*=\s*\$derived\b/);
  if(r){derived.push(r[1]);continue;}
  r=l.match(/^\s*\$derived\.by\(\s*\(\s*\)\s*=>\s*\n\s*\{/);
  if(r){effect.push('derived.by@'+l.trim().slice(0,60));continue;}
  if(l.includes('$effect(')){effect.push('$effect@'+l.trim().slice(0,60));}
}
console.log('STATE_COUNT='+state.length);console.log('STATE='+JSON.stringify(state));
console.log('DERIVED_COUNT='+derived.length);console.log('DERIVED='+JSON.stringify(derived));
console.log('EFFECT='+JSON.stringify(effect));
