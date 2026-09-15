import { asksAboutBibliography } from "./citationResolver";

/** Carry the user's reference target, never the model's claims, into a brief
 * bibliographic followup. A changed document or explicit new topic starts fresh. */
export function bibliographyFollowupQuestion(
  question: string, previousQuestion: string | undefined, sameDocument: boolean
): string {
  if (!sameDocument || !previousQuestion || !asksAboutBibliography(previousQuestion)
      || asksAboutBibliography(question)) return question;
  const bibliographicDetail = /저자|제목|연도|학회|출판|이름|링크|논문명|author|title|year|venue|publisher|doi|full name|link/i;
  const newTopic = /수식|그림|정리|알고리즘|equation|figure|theorem|algorithm|section\s*\d/i;
  if (question.length > 200 || !bibliographicDetail.test(question) || newTopic.test(question)) return question;
  return `${previousQuestion}\nFollow-up: ${question}`;
}
