<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref([])
const err = ref('')
const detail = ref(null)
const detailErr = ref('')
const openId = ref(null)
async function load() {
  try { rows.value = await api.batches() } catch (e) { err.value = e.message }
}
async function toggle(id) {
  detailErr.value = ''
  if (openId.value === id) { openId.value = null; detail.value = null; return }
  try {
    detail.value = await api.batchDetail(id)
    openId.value = id
  } catch (e) { detailErr.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <p class="msg">原批指纹只读：退回不改写批头/明细，退回关联实时重算；点击批次行展开原批对照（钉时明细 + 负向退回链）。</p>
    <p class="msg err" v-if="err">{{ err }}</p>
    <table>
      <thead><tr><th>批次</th><th>业务日</th><th>状态</th><th>笔数</th><th>合计</th><th>退回笔数</th><th>退回落账日</th><th>指纹</th><th>钉扎时刻</th><th>备注</th></tr></thead>
      <tbody>
        <tr v-for="b in rows" :key="b.id" class="clickable" :class="{active: openId===b.id}" @click="toggle(b.id)">
          <td>{{ b.id }}</td>
          <td>{{ b.business_day }}</td>
          <td><span class="tag ok">{{ b.status }}</span></td>
          <td>{{ b.fact_count }}</td>
          <td>{{ b.total_amount }}</td>
          <td>{{ b.ref_return_count }}</td>
          <td>{{ (b.linked_return_days || []).join('、') || '—' }}</td>
          <td><span class="tag" :class="b.fingerprint_intact ? 'ok' : 'bad'">{{ b.fingerprint_intact ? '完好' : '异常' }}</span></td>
          <td>{{ b.sealed_at }}</td>
          <td>{{ b.note }}</td>
        </tr>
      </tbody>
    </table>
    <p class="msg err" v-if="detailErr">{{ detailErr }}</p>
  </div>
  <div class="panel" v-if="detail">
    <h3>批次 #{{ detail.batch.id }} 原批对照（{{ detail.batch.business_day }}）</h3>
    <p class="msg">
      钉时指纹：批头 {{ detail.fingerprint.fact_count }} 笔 / {{ detail.fingerprint.total_amount }}；
      明细重算 {{ detail.fingerprint.sealed_fact_count }} 笔 / {{ detail.fingerprint.sealed_facts_total }}；
      <span class="tag" :class="detail.fingerprint.intact ? 'ok' : 'bad'">{{ detail.fingerprint.intact ? '完好' : '异常' }}</span>
    </p>
    <h4>钉时明细（sealed 事实）</h4>
    <table>
      <thead><tr><th>事实ID</th><th>券码</th><th>活动</th><th>金额</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="f in detail.facts" :key="f.id">
          <td>{{ f.id }}</td><td>{{ f.coupon_code }}</td><td>{{ f.campaign_code }}</td>
          <td>{{ f.amount }}</td>
          <td><span class="tag ok">{{ f.status }}</span></td>
        </tr>
      </tbody>
    </table>
    <h4>关联退回（负向链，落其它业务日）</h4>
    <p class="msg" v-if="!detail.return_facts.length">无退回。</p>
    <table v-else>
      <thead><tr><th>事实ID</th><th>券码</th><th>金额</th><th>落账业务日</th><th>事件</th><th>状态</th><th>原事实</th></tr></thead>
      <tbody>
        <tr v-for="f in detail.return_facts" :key="f.id">
          <td>{{ f.id }}</td><td>{{ f.coupon_code }}</td><td>{{ f.amount }}</td>
          <td>{{ f.business_day }}</td><td>#{{ f.event_id }}</td>
          <td><span class="tag" :class="f.status === 'voided' ? 'muted' : 'warn'">{{ f.status }}</span></td>
          <td>#{{ f.ref_fact_id }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
