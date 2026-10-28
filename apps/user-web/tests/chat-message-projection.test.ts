import assert from 'node:assert/strict'
import test from 'node:test'
import { computed, ref } from 'vue'
import { useChatMessageProjection } from '../src/components/chat/useChatMessageProjection'
import type { ChatMessage } from '../src/components/chat/chatMessage'

test('display projection merges duplicate assistant rows without losing turn metadata', () => {
  const messages = ref<ChatMessage[]>([
    { role: 'assistant', content: 'Hello' },
    { role: 'assistant', content: 'Hello' },
    { role: 'user', content: 'Question' },
    { role: 'assistant', content: 'Answer' },
    { role: 'assistant', content: 'Answer', question_answers: [{
      id: 'question-1', questions: [], answers: [],
    }] },
  ])
  const display = useChatMessageProjection({
    messages: computed(() => messages.value),
    greeting: 'Hello',
    submittedAnswers: () => [],
  })
  assert.equal(display.value.filter(message => message.content === 'Hello').length, 1)
  assert.equal(display.value.filter(message => message.content === 'Answer').length, 1)
  assert.equal(display.value.find(message => message.content === 'Answer')?.question_answers?.length, 1)
})
