const fs = require('fs');
const pd = fs.readFileSync('src/views/project/ProjectDetail.vue', 'utf8');
const ws = fs.readFileSync('src/views/quote/Workspace.vue', 'utf8');
const api = fs.readFileSync('src/api/index.ts', 'utf8');

const checks = [
  ['editQuotation URL 含 from=projects', /editQuotation[\s\S]*?from=projects/.test(pd)],
  ['viewQuotation URL 含 from=projects', /viewQuotation[\s\S]*?from=projects/.test(pd)],
  ['无遗留 console.log', !/console\.log\(['"]编辑/.test(pd)],
  ['entryProjectId 已启用', /const entryProjectId = computed/.test(ws) && !/\/\/ const entryProjectId/.test(ws)],
  ['返回按钮文字正确', /← 返回项目详情/.test(ws)],
  ['goBack 跳 /projects/${id}', /router\.push\(`\/projects\/\$\{entryProjectId\.value\}`\)/.test(ws)],
  ['API 导出 saveProject', /export const saveProject = projectApi\.save/.test(api)],
  ['API 导出 exportProject', /export const exportProject = projectApi\.export/.test(api)]
];

let fail = 0;
checks.forEach(([n, ok]) => { console.log(`${ok ? '✅' : '❌'} ${n}`); if (!ok) fail++; });
console.log(`\n${checks.length - fail}/${checks.length} passed`);
process.exit(fail > 0 ? 1 : 0);
