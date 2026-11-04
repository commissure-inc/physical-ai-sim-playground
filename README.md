# physical-ai-sim-playground

第8回ハンズオン（対面、約120分）向けの、ブラウザだけで動く MuJoCo のプレイグラウンドです。参加される方は URL を開くだけで、インストールも GPU もアカウントも不要です。ページは2つあり、左上のタブで切り替えます。

- **ロボットで遊ぶ**（トップページ）: 強化学習の方策で動いているロボットをその場で操作したり、マウスで押したりして、立ち直るか倒れるかを見ていただきます。
- **係数を変える**（`physics/`）: 摩擦係数、跳ね返りを決める値、質量、時間の刻みをスライダで変え、斜面の箱が滑るか、球が壁をすり抜けるかなどを確かめていただきます。

この回で扱いたいのは、シミュレータが計算できることと、計算できないことです。

シミュレーションはブラウザ内で完結します。サーバは静的ファイルを配信するだけで、計算は参加者のノートパソコン上で行われます。

## 公開 URL

GitHub Pages のソースを GitHub Actions にしたあと、次の URL で開きます。

https://commissure-inc.github.io/physical-ai-sim-playground/

`.github/workflows/deploy.yml` が `main` への push で `dist/` を Pages にデプロイします。Pages を有効にする操作はこのリポジトリのファイルには含まれていません。

## ローカルでビルドして開く

システムに入っている Python 3.9 は使いません。`uv` が Python 3.12 を取得します。依存している [mjswan_playground](https://github.com/ttktjmt/mjswan_playground) は Python 3.11 以上、3.13 未満です。

```sh
uv sync
uv run build
uv run serve
```

ブラウザで http://127.0.0.1:8080/ を開きます。タブを自動で開かないときは `uv run serve --no-open` です。止めるときはターミナルで Ctrl-C を押します。

初回の `uv run build` は、上流のモデルと方策を取得し、mjswan のビューアを組み立てます。数十分かかることがあります。取得したチェックアウトは `~/.cache/mjswan_playground/` に残ります。タスクを1つずつ別プロセスでビルドし、失敗したものは理由を表示して残りを続けます。1つでも失敗したときは、できた分の `dist/` を書いたうえで終了コード 1 になります。

手元で確認するビルドは、URL の基準を `/` にしたままにしてください。`uv run serve` はその配置で配信します。Pages 用のパスはワークフローが次の環境変数で渡します。

```sh
MJSWAN_BASE_PATH=/physical-ai-sim-playground/
```

この値を付けて手元でビルドすると、`uv run serve` ではアセットのパスが合いません。

ファイルが揃っているかの確認は次です。Pages と同じく、COOP/COEP ヘッダのない静的サーバで、`index.html`、スワンの `logo.svg`、wasm、onnx、シーン（`.mjz`）へ HTTP 200 が返ることを見ます。あわせて、出荷した `LICENSE*` / `NOTICE*` とマニフェストの SPDX に、非商用・改変禁止・GPL・CERN-OHL・ライセンスなしが無いかを見ます。当たると終了コードは 1 です。

```sh
uv run verify
```

ビューアが実際に ready になるところまで見るときは、Google Chrome が入っている状態で次を実行します。シーンごとに開き、画面下の「立て直した」「倒れた」が数えられることと、pacman の制御周期も出します。係数を変えるページも、8つのシーンを1つずつ開き、実験では左下に数値が出ることを確かめます。

```sh
uvx --from playwright python scripts/check_browser.py dist
```

係数を変えるページの4つの実験が、画面の説明どおりの結果になるかは、MuJoCo の Python バインディングで同じ値を入れて確かめます（摩擦 0.3 で滑り 0.5 で止まる、減衰比が小さいほど高く跳ねる、重い箱ほど 1 m に着くのが遅い、刻み 0.001 秒では壁で跳ね返り 0.04 秒ではすり抜ける）。

```sh
uv run python scripts/check_physics.py
```

歩行の授業シーンは、出荷した ONNX を 4 秒、前進 0.6 m/s で動かし、基部がどれだけ進み、高さがどれだけ落ちるかを「歩行」と比べます。

```sh
uv run --with onnxruntime python scripts/check_lessons.py dist
```

## 係数を変えるページ

[zalo/mujoco_wasm](https://github.com/zalo/mujoco_wasm)（MIT）に、係数を変える4つの実験を足したものです。ソースとシーンはこのリポジトリの `physics/` にあり、ビルドが `dist/physics/` に写します。

| シーン | 変える値 | 起きること |
| --- | --- | --- |
| 斜面の箱 | 摩擦係数（0.05〜1.0） | 20度の斜面で、約 0.36（tan 20°）より小さいと滑り落ち、大きいと止まる |
| 落下と跳ね返り | 減衰比（0.02〜1.0） | 小さいほど高く跳ねる |
| 押した箱 | 質量（0.2〜5 kg。慣性も同じ比率で変える） | 同じ力で押して、1 m の目印に着くまでの時間が変わる |
| 薄い壁と時間の刻み | 時間の刻み（0.001〜0.05 秒） | 刻みを粗くすると、球が薄い壁をすり抜ける |

ほかに、触って確かめるシーンとして、マグカップ、ロボットの手（Shadow Hand）、布（ハンモック）、人型があります。`physics/?scene=ramp` のように URL でシーンを指定できます（`ramp`、`bounce`、`mass`、`timestep`、`mug`、`hand`、`cloth`、`humanoid`）。

動かすライブラリ（three 0.181.2 と @mujoco/mujoco 3.17.0）はリポジトリに入れていません。ビルドが npm のレジストリから、版と sha512 を固定して取得し、使うファイルだけを `dist/physics/lib/` に写します（`physics.py`）。取得したものは `~/.cache/physical-ai-sim-playground/npm/` に残ります。

## 入っているタスク

いずれも [mjswan_playground](https://github.com/ttktjmt/mjswan_playground)（Apache-2.0、このリポジトリが依存しているコミットは `fc1c034ee5dd29baf60a52b275fef8a46def4426`）のタスクビルダーで組み立てています。ビューアは [mjswan](https://github.com/ttktjmt/mjswan)（Apache-2.0）です。

| タスク | 内容 | 上流 |
| --- | --- | --- |
| unitreerl | Unitree G1 の速度指令による歩行と、その授業用シーン | [unitree_rl_mjlab](https://github.com/unitreerobotics/unitree_rl_mjlab)（Apache-2.0）。G1 のメッシュは MuJoCo Menagerie の [unitree_g1](https://github.com/google-deepmind/mujoco_menagerie/tree/main/unitree_g1)（BSD-3-Clause） |
| booster | Booster K1 の歩行と、その授業用シーン | [booster_deploy](https://github.com/BoosterRobotics/booster_deploy)（Apache-2.0）。ロボットは [booster_assets](https://github.com/BoosterRobotics/booster_assets)（BSD-3-Clause）。ライセンスを書いていない [booster_mjlab](https://github.com/IntelligentRoboticsLab/booster_mjlab) は入れません |
| luwu | XGO の Mini2S、Mini2SW、Lite3 の歩行と、Mini2S / Mini2SW の転倒からの起き上がり | [luwu_mjlab](https://github.com/LuwuDynamics/luwu_mjlab)（Apache-2.0）。方策は [robomotic/XGO](https://huggingface.co/robomotic/XGO)（Apache-2.0） |
| pacman | G1 がボールを避けるシーンと、同じ系統の歩行 | [perceptive_cbf_rl](https://github.com/lzyang2000/perceptive_cbf_rl)（MIT）。G1 のメッシュは BSD-3-Clause |
| leap | LEAP Hand が掌の上で立方体を回す | [in-hand-rotation-mjlab](https://github.com/Msornerrrr/in-hand-rotation-mjlab)（Apache-2.0）。手のモデルは MIT（Copyright 2023 Ananye Agarwal、[LEAP_Hand_Sim](https://github.com/leap-hand/LEAP_Hand_Sim)） |

ブラウザ上の物理演算は [MuJoCo](https://github.com/google-deepmind/mujoco)（Apache-2.0）の WASM ビルドです。ONNX Runtime Web と three.js のライセンス本文は、ビルドが書き出す `dist/THIRD_PARTY_LICENSES.md` に入ります。jszip は MIT と GPL のデュアルライセンスで、このサイトは MIT の側を使います。

G1 と K1 の歩行には、次のシーンがあります。方策そのものは変えていません。

| シーン | 何が違うか |
| --- | --- |
| 歩行 | 上流の歩行のまま |
| 氷の床 | 床と足のすべり摩擦を 0.08 に固定する。通常の床は 1 で、足は起動時に 0.3 から 1.6 のあいだ（G1）。MuJoCo は二つのうち大きい方を使うので、床だけ下げても氷にはなりません |
| 軽い荷物 / 重い荷物 | 胴体の重心に、ロボット質量の約 40% / 約 55% を足す。重心まわりの慣性はそのままです。橙色の箱は見た目だけで、衝突しません |
| 段差 | 前方に高さ 8 cm の箱 |
| 坂 | 前方に 8 度の坂 |

画面の文言は日本語にしてあります。ロボット名、状況、操作のラベルは `localize.py` が `manifest.json` を書き換え、ビューア自身が描くラベル（Scene、Interact、Reset など）は `overlay.py` が差し込むスクリプトで置き換えます。視野角、ポリシーの選択、速度の上限スライダなど、受講者が使わない項目は隠し、指令の矢印は最初は表示しません（`?debug=1` で表示）。マウスの操作は「押す」で始まります。初めて開いたときに「遊び方」を表示します（`?help=0` で出さない）。

画面下に「最初から」「立て直した」「倒れた」「数を0に戻す」があります。数はページの中だけで、サーバには送りません。再読み込みで消えます。接触点と接触力の矢印は、この版の mjswan ビューアにはありません。描画は three.js で、MuJoCo の接触表示フラグを読んでいません。

摩擦をその場のスライダーにするには、イベントが UI の値を読む必要があります。mjswan のイベント追跡はコマンドを渡さないので、シーンを分けることにしました。

このビルドの `dist/` は 190 MB です。G1 の歩行一式が 58 MB、K1 が 40 MB、luwu が 20 MB、pacman が 22 MB、leap が 3 MB、係数を変えるページが 19 MB で、残りはビューアです。同じ歩行のシーンは方策とモデルをコピーしているので、その分が大きくなっています。受講者が1つのシーンを開いたときに読み込むのは、ビューアとそのシーンだけで、31〜40 MB です（ヘッドレス Chrome で計測）。係数を変えるページは、開いたときに全シーンをまとめて読み込みます（約 19 MB）。

## ライセンス上の注意

有償の企業研修で、企業のサイトに載せるため、非商用・コピーレフト・ライセンスのない資産は入れていません。

- microduck の STL は CC BY-NC-SA 4.0 として記録されるため、タスクごと外しています。
- unitreerl のダンスは LAFAN1 `dance1_subject2`（CC BY-NC-ND 4.0）です。歩行シーンはこのクリップを使わないので、ダンスシーンと `dance_1_subject_2.npz` はビルドしません。
- booster のダンスと格闘は、元のモーションデータセットの名前が booster_deploy に書いてないため、サイトから外しています（`localize.py` の `DROP_SCENES`）。

詳細は `NOTICE` に書いてあります。

## mjswan のスワン

mjswan は、商用や企業のページでも、操作パネルのスワンのアイコンと、それを押して開くダイアログを残すよう求めています。このサイトは mjswan のビューアをそのまま載せており、アイコンもダイアログも外していません。

## ライセンス

このリポジトリのコードは [Apache-2.0](LICENSE) です。上流のプロジェクトと、非商用の資産は [NOTICE](NOTICE) に列挙しています。
