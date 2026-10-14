import {
  browserLocalPersistence,
  GoogleAuthProvider,
  onAuthStateChanged,
  setPersistence,
  signInWithPopup,
  signOut,
  type User,
} from "firebase/auth";
import { auth } from "./firebase";

export async function loginWithGoogle(): Promise<User> {
  // 意思伝達装置の PC ではログインしたまま維持する
  await setPersistence(auth, browserLocalPersistence);
  const cred = await signInWithPopup(auth, new GoogleAuthProvider());
  return cred.user;
}

export const logout = () => signOut(auth);

export const watchAuth = (cb: (user: User | null) => void) => onAuthStateChanged(auth, cb);

/** API 呼び出し用の ID トークン（期限が近ければ SDK が自動更新する）。 */
export async function getIdToken(): Promise<string> {
  const user = auth.currentUser;
  if (!user) throw new Error("ログインしていません");
  return user.getIdToken();
}
