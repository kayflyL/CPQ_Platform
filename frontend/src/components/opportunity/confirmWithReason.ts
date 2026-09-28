import { h, ref } from 'vue'
import { Input, message, Modal } from 'ant-design-vue'

/** 必填原因的确认弹窗（退回等流程动作用）：原因为空不放行，接口报错留在弹窗内提示。 */
export function confirmWithReason(options: {
  title: string
  hint?: string
  okText?: string
  placeholder?: string
  onOk: (reason: string) => Promise<void>
}) {
  const reason = ref('')
  Modal.confirm({
    title: options.title,
    content: () => h('div', null, [
      ...(options.hint
        ? [h('p', {
            style: 'margin: 0 0 10px; color: var(--cpq-text-secondary, #888); font-size: 12px; line-height: 1.6;',
          }, options.hint)]
        : []),
      h(Input.TextArea, {
        value: reason.value,
        'onUpdate:value': (v: string) => { reason.value = v },
        rows: 3,
        placeholder: options.placeholder || '请填写原因（必填）',
      }),
    ]),
    okText: options.okText || '确定',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      const text = reason.value.trim()
      if (!text) {
        message.warning(options.placeholder || '请填写原因')
        return Promise.reject(new Error('empty'))
      }
      try {
        await options.onOk(text)
      } catch (e: any) {
        if (e?.message === 'empty') return Promise.reject(e)
        message.error(e?.response?.data?.detail || '操作失败')
        return Promise.reject(e)
      }
    },
  })
}
