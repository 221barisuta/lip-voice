// Firestore / Storage ルールのテスト。エミュレータ起動中に実行する:
//   firebase emulators:start --only firestore,storage  →  npm test
import { initializeTestEnvironment, assertFails, assertSucceeds } from "@firebase/rules-unit-testing";
import { doc, getDoc, setDoc } from "firebase/firestore";
import { ref, getBytes, uploadBytes } from "firebase/storage";
import { readFileSync } from "node:fs";
import { after, before, test } from "node:test";

let env;
before(async () => {
  env = await initializeTestEnvironment({
    projectId: "demo-lipvoice-rules",
    firestore: { rules: readFileSync("../firestore.rules", "utf8"), host: "127.0.0.1", port: 8081 },
    storage: { rules: readFileSync("../storage.rules", "utf8"), host: "127.0.0.1", port: 9199 },
  });
  await env.withSecurityRulesDisabled(async (ctx) => {
    await setDoc(doc(ctx.firestore(), "users/alice/clips/c1"), { phrase_id: "p01" });
    await setDoc(doc(ctx.firestore(), "users/bob/clips/c1"), { phrase_id: "p01" });
    await uploadBytes(ref(ctx.storage(), "users/alice/clips/c1.json"), new Uint8Array([1]));
    await uploadBytes(ref(ctx.storage(), "models/alice/latest.pt"), new Uint8Array([1]));
  });
});
after(() => env.cleanup());

test("firestore: 本人は自分のデータを読める", async () => {
  const db = env.authenticatedContext("alice").firestore();
  await assertSucceeds(getDoc(doc(db, "users/alice/clips/c1")));
});
test("firestore: 他人のデータは読めない", async () => {
  const db = env.authenticatedContext("alice").firestore();
  await assertFails(getDoc(doc(db, "users/bob/clips/c1")));
});
test("firestore: 未ログインは読めない", async () => {
  await assertFails(getDoc(doc(env.unauthenticatedContext().firestore(), "users/alice/clips/c1")));
});
test("firestore: 本人でもクライアントから書けない（書き込みはサーバー経由のみ）", async () => {
  const db = env.authenticatedContext("alice").firestore();
  await assertFails(setDoc(doc(db, "users/alice/clips/c2"), { phrase_id: "p01" }));
});
test("firestore: users 以外は読み書き不可", async () => {
  const db = env.authenticatedContext("alice").firestore();
  await assertFails(getDoc(doc(db, "other/x")));
});
test("storage: 本人は自分の録画・モデルを読める", async () => {
  const st = env.authenticatedContext("alice").storage();
  await assertSucceeds(getBytes(ref(st, "users/alice/clips/c1.json")));
  await assertSucceeds(getBytes(ref(st, "models/alice/latest.pt")));
});
test("storage: 他人・未ログインは読めない", async () => {
  await assertFails(getBytes(ref(env.authenticatedContext("bob").storage(), "users/alice/clips/c1.json")));
  await assertFails(getBytes(ref(env.unauthenticatedContext().storage(), "users/alice/clips/c1.json")));
});
test("storage: 本人でも書けない（モデル差し替え防止）", async () => {
  const st = env.authenticatedContext("alice").storage();
  await assertFails(uploadBytes(ref(st, "models/alice/latest.pt"), new Uint8Array([9])));
  await assertFails(uploadBytes(ref(st, "users/alice/clips/c9.json"), new Uint8Array([9])));
});
