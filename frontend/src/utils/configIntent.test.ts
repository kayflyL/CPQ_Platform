/** 配置意图识别单测 —— node 原生 test runner：node --test frontend/src/utils/configIntent.test.ts */
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isConfigIntent, hasServerWord, configIntentWords } from './configIntent.ts'

test('强配置意图：直接进入需求分析', () => {
  assert.equal(isConfigIntent('帮我配一台服务器，2U，预算20万'), true)
  assert.equal(isConfigIntent('我要配置服务器，主要跑数据库'), true)
  assert.equal(isConfigIntent('这台服务器怎么配？'), true)
  assert.equal(isConfigIntent('帮我做一下需求分析'), true)
  assert.equal(isConfigIntent('生成整机方案'), true)
  assert.equal(isConfigIntent('给个报价'), true)
})

test('弱意图：不自动进入，交按钮兜底', () => {
  assert.equal(isConfigIntent('我想买台服务器'), false)
  assert.equal(isConfigIntent('服务器什么价格'), false)
  assert.equal(isConfigIntent('你好'), false)
  assert.equal(isConfigIntent(''), false)
})

test('提到服务器：弱意图按钮触发条件', () => {
  assert.equal(hasServerWord('我想买台服务器'), true)
  assert.equal(hasServerWord('这台机器多少钱'), true)
  assert.equal(hasServerWord('你好'), false)
})

test('自定义词表优先于默认（可配）', () => {
  const custom = ['自定义词']
  assert.equal(isConfigIntent('自定义词开头的需求', custom), true)
  assert.equal(isConfigIntent('帮我配台服务器', custom), false) // 自定义词表覆盖默认
  assert.equal(configIntentWords([]).length > 0, true)
  assert.deepEqual(configIntentWords(['  配置服务器 ', '']), ['配置服务器'])
})
