<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const preview = ref(null)
const allFacts = ref([])
const msg = ref('')
const err = ref('')
const retForm = ref({ coupon_code: '', business_day: '', note: '' })
const retMsg = ref('')
const retErr = ref('')

async function load() {
  err.value = ''
  try {
    preview.value = await api.preview()
    allFacts.value = await api.facts()
  } catch (e) { err.value = e.message }
}
async function seal() {
  msg.value = ''; err.value = ''
  try {
    const r = await api.seal({})
    msg.value = `已钉扎批次 #${r.batch_id} · ${r.fact_count} 笔 · 合计 ${r.total_amount}`
    await load()
  } catch (e) { err.value = e.message }
}
async function doReturn() {
  retMsg.value = ''; retErr.value = ''
  try {
    const body = { coupon_code: retForm.value.coupon_code.trim() }
    if (retForm.value.business_day) body.business_day = retForm.value.business_day
    if (retForm.value.note) body.note = retForm.value.note
    const r = await api.returnRedeem(body)
    retMsg.value = r.policy === 'void'
      ? `未钉冲销：事实 #${r.fact_id} 已作废（void 事件 #${r.event_id}，${r.amount}），预览合计同步减少`
      : `已钉退回成功：事件 #${r.event_id} 与负向事实 #${r.fact_id} 齐套落账 ${r.business_day}（open，待钉）；原批 #${r.original_batch_id ?? '—'} 指纹未回改，可在批次列表点开对照`
    retForm.value.coupon_code = ''
    await load()
  } catch (e) { retErr.value = e.message }
}
function statusTag(s) {
  return s === 'sealed' ? 'ok' : s === 'voided' ? 'muted' : 'warn'
}
onMounted(load)
</script>
<template>
  <div class="panel" v-if="preview">
    <div class="grid">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ preview.business_day }}</div></div>
      <div class="stat"><div class="k">待钉笔数</div><div class="v ticket">{{ preview.open_count }}</div></div>
      <div class="stat"><div class="k">待钉合计</div><div class="v ticket">{{ preview.open_total }}</div></div>
      <div class="stat"><div class="k">已钉扎</div><div class="v">{{ preview.already_sealed ? '是' : '否' }}</div></div>
    </div>
    <div class="row">
      <button type="button" @click="seal" :disabled="preview.already_sealed || preview.open_count===0">钉扎本日核销</button>
      <button type="button" class="ghost" @click="load">刷新预览</button>
    </div>
    <p class="msg" v-if="msg">{{ msg }}</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
  <div class="panel">
    <div class="row">
      <label>退回券码 <input v-model="retForm.coupon_code" placeholder="C-1001" /></label>
      <label>落账业务日 <input v-model="retForm.business_day" placeholder="可空=当前业务日" /></label>
      <label>备注 <input v-model="retForm.note" placeholder="可空" /></label>
      <button type="button" @click="doReturn" :disabled="!retForm.coupon_code.trim()">退回 / 冲销</button>
    </div>
    <p class="msg">未钉事实 → 原业务日冲销作废；已钉事实 → 退回只落到其它业务日的负向事实，原批永不回改。</p>
    <p class="msg" v-if="retMsg">{{ retMsg }}</p>
    <p class="msg err" v-if="retErr">{{ retErr }}</p>
  </div>
  <div class="panel">
    <table>
      <thead><tr><th>事实ID</th><th>类型</th><th>券码</th><th>活动</th><th>金额</th><th>状态</th><th>关联事实</th></tr></thead>
      <tbody>
        <tr v-for="f in allFacts" :key="f.id">
          <td>{{ f.id }}</td>
          <td>{{ f.kind === 'return' ? '退回' : '核销' }}</td>
          <td>{{ f.coupon_code }}</td>
          <td>{{ f.campaign_code }}</td>
          <td>{{ f.amount }}</td>
          <td><span class="tag" :class="statusTag(f.status)">{{ f.status }}</span></td>
          <td>{{ f.ref_fact_id ? `#${f.ref_fact_id}` : '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
