import { computed, type ComputedRef } from 'vue'
import { expandQuestionAnswers, type QuestionAnswerEntry } from './questionAnswerHistory'
import type { ChatMessage } from './chatMessage'

export function useChatMessageProjection(options: {
  messages: ComputedRef<ChatMessage[]>
  greeting: string
  submittedAnswers: () => QuestionAnswerEntry[]
}) {
  return computed(() => {
    const result: ChatMessage[] = []
    const greeting = options.greeting.trim()
    let hasGreeting = false
    for (const message of options.messages.value) {
      const content = message.content?.trim() || ''
      if (message.role === 'assistant' && content === greeting) {
        if (hasGreeting) continue
        hasGreeting = true
      }
      const previous = result[result.length - 1]
      if (previous?.role === 'assistant' && message.role === 'assistant' &&
          (previous.content?.trim() || '') === content) {
        // Retain data that can arrive on either the optimistic or server row.
        if (message._codeChanges && !previous._codeChanges) {
          result[result.length - 1] = { ...previous, _codeChanges: message._codeChanges }
        }
        if (message.question_answers?.length && !previous.question_answers?.length) {
          result[result.length - 1] = {
            ...result[result.length - 1], question_answers: message.question_answers,
          }
        }
        continue
      }
      result.push(message)
    }
    return expandQuestionAnswers(result, options.submittedAnswers())
  })
}
