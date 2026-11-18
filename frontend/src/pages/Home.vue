<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'

const d = ref(null)
const err = ref('')
async function load() {
  err.value = ''
  try { d.value = await api.dashboard() } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <div class="grid" v-if="d">
      <div class="stat"><div class="k">业务日</div><div class="v">{{ d.business_day }}</div></div>
      <div class="stat"><div class="k">今日事件</div><div class="v">{{ d.event_count }}</div></div>
      <div class="stat"><div class="k">在效事实</div><div class="v ticket">{{ d.fact_count }}</div></div>
      <div class="stat"><div class="k">待钉 open</div><div class="v">{{ d.open_fact_count }}</div></div>
      <div class="stat"><div class="k">已冲销 voided</div><div class="v">{{ d.voided_fact_count }}</div></div>
      <div class="stat"><div class="k">今日核销净额</div><div class="v ticket">{{ d.redeem_total_today }}</div></div>
      <div class="stat"><div class="k">日已钉扎</div><div class="v">{{ d.day_sealed ? '是' : '否' }}</div></div>
      <div class="stat"><div class="k">退回 open</div><div class="v">{{ d.return_open_count }}</div></div>
    </div>
    <p class="msg" v-if="!err">合计只认在效事实（open+sealed）；退回单一入口：未钉冲销作废事实，已钉退回落到其它业务日的负向事实。</p>
    <p class="msg err" v-if="err">{{ err }}</p>
  </div>
</template>
