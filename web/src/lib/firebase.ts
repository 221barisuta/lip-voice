import { initializeApp } from "firebase/app";
import { connectAuthEmulator, getAuth } from "firebase/auth";

// 接続情報はすべて .env.* の VITE_ 変数から読む（コードに値を書かない）
const app = initializeApp({
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
});

export const auth = getAuth(app);

// ローカル検証用: Auth エミュレータを使う時だけ設定する（本番・dev の配置では空）
const emulator = import.meta.env.VITE_AUTH_EMULATOR_URL as string | undefined;
if (emulator) connectAuthEmulator(auth, emulator, { disableWarnings: true });
