<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref([])
const err = ref('')
async function load() {
  try { rows.value = await api.batches() } catch (e) { err.value = e.message }
}
onMounted(load)
</script>
<template>
  <div class="panel">
    <p class="msg">批次列表不展示退回关联日；合计以批头为准（退回后可能已改写）。</p>
    <p class="msg err" v-if="err">{{ err }}</p>
    <table>
      <thead><tr><th>批次</th><th>业务日</th><th>状态</th><th>笔数</th><th>合计</th><th>钉扎时刻</th><th>备注</th></tr></thead>
      <tbody>
        <tr v-for="b in rows" :key="b.id">
          <td>{{ b.id }}</td>
          <td>{{ b.business_day }}</td>
          <td><span class="tag ok">{{ b.status }}</span></td>
          <td>{{ b.fact_count }}</td>
          <td>{{ b.total_amount }}</td>
          <td>{{ b.sealed_at }}</td>
          <td>{{ b.note }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
