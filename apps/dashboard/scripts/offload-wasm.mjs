/**
 * DuckDB-WASM を Cloudflare R2 へ退避する post-build ステップ。
 *
 * Evidence はブラウザ用 DuckDB-WASM（duckdb-eh / duckdb-mvp、各 33〜38MiB）を build に同梱するが、
 * Cloudflare Pages / Workers は「1ファイル 25MiB」上限のためアップロードが弾かれる。
 * そこでビルド後に:
 *   1. 2つの wasm を R2 バケットへ upload（--content-type application/wasm）
 *   2. wasm を参照する極小ローダー（build/_app/immutable/chunks/duckdb-*.js。
 *      `const a="/_app/immutable/assets/duckdb-eh.<hash>.wasm";export{a as default};`）の
 *      URL を R2 の絶対URLへ書き換え
 *   3. 25MiB 超の wasm 本体を build から除去（→ pages deploy が通る）
 *
 * 参照はこのローダー2ファイルの文字列定数1つだけなので、置換は堅牢（他 48 チャンクは不変）。
 * ブラウザは R2 から直接 fetch するため、バケットに CORS（r2-cors.json）と public アクセスが要る。
 *
 * R2_PUBLIC_BASE は下の定数に焼き込み済み（通常 env 不要）。
 * R2 有効化・バケット初回セットアップの手順は README のデプロイ節を参照。
 */
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";

const BUILD = "build";
const CHUNKS = path.join(BUILD, "_app/immutable/chunks");
const R2_BUCKET = process.env.R2_BUCKET ?? "data-forge-dashboard-assets";
// R2 公開URL（非機密・バケット単位で固定）。既定値に焼き込むので通常は env 不要。
// 別バケットを使う場合のみ R2_BUCKET と R2_PUBLIC_BASE を env で上書きする。
const R2_PUBLIC_BASE = (
  process.env.R2_PUBLIC_BASE ?? "https://pub-07daec6c2da94111b20e743f906161a9.r2.dev"
).replace(/\/+$/, "");

const WASM_REF = /"(\/_app\/immutable\/assets\/(duckdb-[^"]+\.wasm))"/;

function die(msg) {
  console.error(`[offload-wasm] ✗ ${msg}`);
  process.exit(1);
}

if (!R2_PUBLIC_BASE) {
  die("R2_PUBLIC_BASE が空（空文字で上書きされている）。offload-wasm.mjs の既定値か env を確認。");
}

async function existsOnR2(url) {
  try {
    return (await fetch(url, { method: "HEAD" })).ok;
  } catch {
    return false;
  }
}

const loaders = existsSync(CHUNKS)
  ? readdirSync(CHUNKS).filter((f) => /^duckdb-(eh|mvp)\.[^.]+\.js$/.test(f))
  : [];
if (loaders.length === 0) die(`duckdb ローダーチャンクが見つからない（${CHUNKS}）。先にビルドが必要。`);

let offloaded = 0;
for (const loader of loaders) {
  const loaderPath = path.join(CHUNKS, loader);
  const js = readFileSync(loaderPath, "utf8");
  const m = js.match(WASM_REF);
  if (!m) {
    if (js.includes(R2_PUBLIC_BASE)) {
      console.log(`  = ${loader} は退避済み（skip）`);
      continue;
    }
    die(`${loader}: wasm 参照が見つからない（Evidence の出力形式が変わった可能性）`);
  }

  const wasmName = m[2]; // duckdb-eh.<hash>.wasm
  const localFile = path.join(BUILD, m[1].replace(/^\//, ""));
  const url = `${R2_PUBLIC_BASE}/${wasmName}`;
  if (!existsSync(localFile)) die(`${wasmName} が build に無い（${localFile}）`);
  const sizeMiB = (statSync(localFile).size / 1024 / 1024).toFixed(1);

  if (await existsOnR2(url)) {
    console.log(`  = r2://${R2_BUCKET}/${wasmName} 既存（upload skip, ${sizeMiB}MiB）`);
  } else {
    console.log(`  ↑ upload ${wasmName} (${sizeMiB}MiB) → r2://${R2_BUCKET}`);
    execFileSync(
      "wrangler",
      [
        "r2", "object", "put", `${R2_BUCKET}/${wasmName}`,
        "--file", localFile,
        "--remote",
        "--content-type", "application/wasm",
        "--cache-control", "public, max-age=31536000, immutable",
      ],
      { stdio: "inherit" },
    );
  }

  writeFileSync(loaderPath, js.replace(`"${m[1]}"`, `"${url}"`)); // ローダーを R2 URL へ
  rmSync(localFile); // 25MiB 超を build から除去
  console.log(`  ✓ ${loader} → ${url}`);
  offloaded += 1;
}

console.log(`[offload-wasm] ✓ ${offloaded} 個の wasm を R2 へ退避（build から除去済み）`);
