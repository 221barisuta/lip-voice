export interface Phrase {
  id: string;
  text: string;
}

/** フレーズ編集画面の 1 行（本数・日数・モデルに入っているか） */
export interface PhraseInfo extends Phrase {
  clips: number;
  days: number;
  in_model: boolean;
}
