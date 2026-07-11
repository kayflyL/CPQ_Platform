const fs = require('fs');
const content = fs.readFileSync('src/components/quote/ProjectFiles.vue', 'utf-8');

const checks = [
  { name: '拖拽事件绑定', test: () => content.includes('@dragover.prevent="handleDragOver"') && content.includes('@drop.prevent="handleDrop"') },
  { name: '拖拽状态变量', test: () => content.includes('const isDragging = ref(false)') },
  { name: 'handleDragOver 函数', test: () => content.includes('const handleDragOver') && content.includes('isDragging.value = true') },
  { name: 'handleDrop 函数', test: () => content.includes('const handleDrop') && content.includes('e.dataTransfer?.files') },
  { name: '拖拽视觉反馈', test: () => content.includes(':class="{ \'dragging\': isDragging }"') && content.includes('释放文件以上传') },
  { name: '拖拽样式', test: () => content.includes('.files-list.dragging') && content.includes('.drag-overlay') }
];

console.log('🔍 验证拖拽上传功能...\n');
let passed = 0;
checks.forEach(c => {
  const ok = c.test();
  console.log(`${ok ? '✅' : '❌'} ${c.name}`);
  if (ok) passed++;
});
console.log(`\n结果: ${passed}/${checks.length} 通过`);
process.exit(passed === checks.length ? 0 : 1);
