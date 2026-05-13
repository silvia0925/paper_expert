# paper-expert Agent 浣跨敤鎵嬪唽

> 涓€涓潰鍚戠鐮斾汉鍛樼殑 AI 璁烘枃绠＄悊涓庣爺绌跺姪鎵?
---

## 鐩綍

1. [瀹夎](#1-瀹夎)
2. [鍒濆閰嶇疆](#2-鍒濆閰嶇疆)
3. [鎼滅储璁烘枃](#3-鎼滅储璁烘枃)
4. [娣诲姞璁烘枃](#4-娣诲姞璁烘枃)
5. [鎵归噺瀵煎叆](#5-鎵归噺瀵煎叆)
6. [绠＄悊鐭ヨ瘑搴揮(#6-绠＄悊鐭ヨ瘑搴?
7. [闃呰璁烘枃](#7-闃呰璁烘枃)
8. [鎻愰棶锛圦A锛塢(#8-鎻愰棶qa)
9. [鐢熸垚鏂囩尞缁艰堪](#9-鐢熸垚鏂囩尞缁艰堪)
10. [鐮旂┒鏂瑰悜寤鸿](#10-鐮旂┒鏂瑰悜寤鸿)
11. [棰嗗煙涓撳妯″紡](#11-棰嗗煙涓撳妯″紡)
12. [閰嶇疆鍙傝€僝(#12-閰嶇疆鍙傝€?
13. [甯歌闂](#13-甯歌闂)

---

## 1. 瀹夎

```bash
# 鍏嬮殕椤圭洰
git clone <repo-url> paper-expert-agent
cd paper-expert-agent

# 瀹夎锛堟帹鑽愮敤铏氭嫙鐜锛?pip install -e .
```

瀹夎瀹屾垚鍚庯紝缁堢杈撳叆 `paper-expert` 鍗冲彲浣跨敤銆?
---

## 2. 鍒濆閰嶇疆

### 2.1 鏈€灏忛厤缃紙鍙敤鎼滅储鍜岀鐞嗗姛鑳斤級

涓嶉渶瑕佷换浣曢厤缃紝寮€绠卞嵆鐢ㄣ€?
### 2.2 鎺ㄨ崘閰嶇疆锛堝惎鐢?QA銆佺患杩扮瓑 AI 鍔熻兘锛?
```bash
# 璁剧疆 OpenAI 鍏煎鐨?API Key锛堝繀闇€锛岀敤浜?QA/缁艰堪/涓撳妯″紡锛?paper-expert config set api_keys.openai sk-浣犵殑key

# 濡傛灉浣跨敤绗笁鏂?API 浠ｇ悊锛堝杞彂鏈嶅姟锛夛紝璁剧疆浠ｇ悊鍦板潃
paper-expert config set llm.api_base https://api.浣犵殑浠ｇ悊.com/v1

# 璁剧疆妯″瀷锛堥粯璁?gpt-4o锛屾寜浣犵殑浠ｇ悊鏀寔鐨勬ā鍨嬫敼锛?paper-expert config set llm.cloud_model openai/gpt-5.2

# 璁剧疆 Unpaywall 閭锛堝彲閫夛紝鎻愰珮 PDF 鑷姩鑾峰彇鎴愬姛鐜囷級
paper-expert config set api_keys.unpaywall_email 浣犵殑閭@xxx.com
```

### 2.3 鍒濆鍖栧垎绫昏瘝琛?
```bash
paper-expert lib vocab --init
```

杩欎細鍔犺浇榛樿鐨?AI + 璁＄畻鍏夊埢棰嗗煙鏈锛岀敤浜庤鏂囪嚜鍔ㄥ垎绫汇€?
### 2.4 鏌ョ湅褰撳墠閰嶇疆

```bash
paper-expert config show
```

---

## 3. 鎼滅储璁烘枃

浠?Semantic Scholar銆丱penAlex銆乤rXiv 绛夊涓鏈暟鎹簱鍚屾椂鎼滅储銆?
```bash
# 鍩虹鎼滅储
paper-expert search "GAN for optical proximity correction"

# 闄愬畾骞翠唤
paper-expert search "inverse lithography" --year 2023-2025

# 闄愬畾鏁版嵁婧?paper-expert search "transformer attention" --source arxiv

# 闄愬埗缁撴灉鏁伴噺
paper-expert search "mask optimization" --limit 5

# 鎼滃埌鐩存帴涓嬭浇鍏ュ簱
paper-expert search "neural OPC" --download
```

鎼滅储缁撴灉浼氭樉绀鸿鏂囨爣棰樸€佷綔鑰呫€佸勾浠姐€佸紩鐢ㄦ暟銆佹槸鍚︽湁鍏嶈垂 PDF銆?
---

## 4. 娣诲姞璁烘枃

### 4.1 鎸?ID 娣诲姞

```bash
# 閫氳繃 arXiv ID
paper-expert add arxiv:2401.12345

# 閫氳繃 DOI
paper-expert add doi:10.1109/TCAD.2019.2939329

# 閫氳繃 Semantic paper-expert ID
paper-expert add s2:204e3073870fae3d05bcbc2f6a8e263d9b72e776
```

绯荤粺浼氳嚜鍔細鑾峰彇鍏冩暟鎹?鈫?灏濊瘯涓嬭浇 PDF 鈫?瑙ｆ瀽鍒嗙被 鈫?瀛樺叆鐭ヨ瘑搴撱€?
### 4.2 娣诲姞鏈湴 PDF

```bash
# 鐩存帴娣诲姞涓€涓?PDF 鏂囦欢
paper-expert add ~/Downloads/paper.pdf

# 涓哄凡鏈夌殑 metadata-only 璁烘枃琛ュ厖 PDF
paper-expert add doi:10.1109/xxx --pdf ~/Downloads/paper.pdf
```

---

## 5. 鎵归噺瀵煎叆

### 5.1 浠?BibTeX 瀵煎叆

```bash
paper-expert import references.bib
```

### 5.2 浠庢湰鍦版枃浠跺す瀵煎叆

```bash
# 閫掑綊鎵弿鏂囦欢澶逛腑鎵€鏈?PDF
paper-expert import ~/papers/ --recursive
```

### 5.3 浠?Zotero 瀵煎叆

```bash
paper-expert import ~/Zotero/ --zotero
```

瀵煎叆鏃朵細鏄剧ず杩涘害鏉★紝鑷姩璺宠繃宸叉湁璁烘枃锛堟寜 DOI 鍘婚噸锛夈€?
---

## 6. 绠＄悊鐭ヨ瘑搴?
### 6.1 鏌ョ湅璁烘枃鍒楄〃

```bash
# 鍒楀嚭鏈€杩戞坊鍔犵殑璁烘枃
paper-expert lib list

# 鎸夋爣绛捐繃婊?paper-expert lib list --tag "OPC"

# 鎸夊勾浠借繃婊?paper-expert lib list --year 2024

# 鎸夌姸鎬佽繃婊わ紙full-text = 鏈塒DF锛宮etadata-only = 浠呭厓鏁版嵁锛?paper-expert lib list --state full-text

# 鎸夊紩鐢ㄦ暟鎺掑簭
paper-expert lib list --sort citations

# 缁勫悎浣跨敤
paper-expert lib list --tag "Bei Yu" --year 2021 --sort citations --limit 50
```

### 6.2 鎵撴爣绛?
```bash
# 娣诲姞鏍囩
paper-expert lib tag 42 --add "閲嶈" --add "寰呭鐜?

# 鍒犻櫎鏍囩
paper-expert lib tag 42 --remove "寰呭鐜?
```

### 6.3 鑷姩鍒嗙被

```bash
# 瀵规湭鍒嗙被鐨勮鏂囪繍琛?LLM 鑷姩鍒嗙被锛堥渶瑕佹湰鍦?Ollama锛?paper-expert lib classify
```

绯荤粺浣跨敤涓夊眰鍒嗙被锛?- **L0锛堣嚜鍔級**锛氬ぇ鏂瑰悜锛屽 AI銆丆omputational Lithography銆丆ross-domain
- **L1锛圠LM锛?*锛氱粏鍒嗘柟鍚戯紝濡?GAN銆丱PC銆両LT锛堥渶瑕?Ollama 鏈湴妯″瀷锛?- **L2锛堟墜鍔級**锛氫綘鑷繁鐨勬爣绛撅紝濡?"閲嶈"銆?寰呰"

### 6.4 鏌ョ湅缁熻

```bash
paper-expert lib stats
```

鏄剧ず锛氳鏂囨€绘暟銆佹寜鐘舵€?鍒嗙被/骞翠唤/鏈熷垔鐨勫垎甯冦€佸瓨鍌ㄥぇ灏忋€?
### 6.5 绠＄悊鍒嗙被璇嶈〃

```bash
# 鏌ョ湅褰撳墠璇嶈〃
paper-expert lib vocab

# 娣诲姞鏂版湳璇?paper-expert lib vocab --add "EUV" --aliases "extreme ultraviolet, EUVL"

# 鍒濆鍖栭粯璁よ瘝琛?paper-expert lib vocab --init
```

### 6.6 瀵煎嚭

```bash
# 瀵煎嚭涓?BibTeX
paper-expert lib export --format bibtex --tag "OPC" --output refs.bib

# 瀵煎嚭涓?CSV
paper-expert lib export --format csv --output papers.csv
```

### 6.7 杩佺Щ鏃?PDF 鍒板垎绫绘枃浠跺す

```bash
paper-expert lib migrate-pdfs
```

鎶婁箣鍓嶄笅杞藉埌 `pdfs/` 鏍圭洰褰曠殑 PDF 鑷姩绉诲叆鍒嗙被瀛愭枃浠跺す锛堝 `pdfs/AI/`锛夈€?
### 6.8 閲嶅缓鍚戦噺绱㈠紩

```bash
paper-expert lib rebuild-index
```

濡傛灉鍚戦噺绱㈠紩鎹熷潖锛屽彲浠?PDF 鏂囦欢閲嶅缓銆?
---

## 7. 闃呰璁烘枃

```bash
# 鏌ョ湅璁烘枃璇︽儏锛堝厓鏁版嵁 + 鎽樿锛?paper-expert read 42

# 鏌ョ湅瑙ｆ瀽鍚庣殑鍏ㄦ枃
paper-expert read 42 --full

# 鏌ョ湅寮曠敤鍏崇郴锛堣繖绡囧紩浜嗚皝锛岃皝寮曚簡瀹冿級
paper-expert read 42 --citations

# AI 鐢熸垚缁撴瀯鍖栨憳瑕侊紙闇€瑕佷簯绔?LLM锛?paper-expert read 42 --summary
```

---

## 8. 鎻愰棶锛圦A锛?
鍩轰簬浣犵煡璇嗗簱涓殑璁烘枃鍥炵瓟闂锛岃嚜鍔ㄥ紩鐢ㄦ潵婧愩€?
```bash
# 鍩虹闂瓟
paper-expert ask "What are the main approaches to neural OPC?"

# 闄愬畾鑼冨洿锛堝彧鎼滅储鐗瑰畾鏍囩鐨勮鏂囷級
paper-expert ask "Compare ILT acceleration methods" --scope tag:OPC

# 闄愬畾骞翠唤鑼冨洿
paper-expert ask "Latest advances in EUV resist" --scope year:2024-2025

# 鑷姩琛ユ锛氱瓟妗堜笉澶熸椂鑷姩鎼滅储涓嬭浇鏂拌鏂囧啀鍥炵瓟
paper-expert ask "How does KAN accelerate ILT?" --auto-fetch

# 闄愬埗鑷姩涓嬭浇鏁伴噺
paper-expert ask "..." --auto-fetch --fetch-limit 3
```

> **鍓嶆彁**锛氶渶瑕侀厤缃簯绔?LLM API key锛屼笖鐭ヨ瘑搴撲腑闇€瑕佹湁 full-text锛堟湁 PDF锛夌殑璁烘枃銆?
---

## 9. 鐢熸垚鏂囩尞缁艰堪

鑷姩鐢熸垚鏈夊鏈粨鏋勭殑鏂囩尞缁艰堪锛屼笉鏄畝鍗曠殑鎽樿鎷兼帴銆?
```bash
# 鐢熸垚缁艰堪
paper-expert review "neural approaches to inverse lithography"

# 闄愬畾鑼冨洿
paper-expert review "OPC acceleration" --scope year:2022-2025

# 璁烘枃涓嶅鏃惰嚜鍔ㄨˉ鍏?paper-expert review "KAN for lithography" --auto-fetch

# 淇濆瓨鍒版枃浠?paper-expert review "neural OPC" --output review.md

# 閲嶆柊鐢熸垚锛堝拷鐣ョ紦瀛橈級
paper-expert review "neural OPC" --refresh

# 鏄剧ず鍚勯樁娈佃繘搴?paper-expert review "neural OPC" --verbose
```

鐢熸垚鐨勭患杩板寘鍚細
1. **Introduction** 鈥?鐮旂┒鑳屾櫙
2. **Methodology Taxonomy** 鈥?鏂规硶鍒嗙被
3. **Detailed Analysis** 鈥?姣忕被鏂规硶鐨勮缁嗗垎鏋愪笌璁烘枃瀵规瘮
4. **Discussion** 鈥?璺ㄧ被鐨勫叡璇嗐€佺煕鐩俱€佽秼鍔?5. **Research Gaps** 鈥?鐮旂┒绌虹櫧鍜屾湭鏉ユ柟鍚?6. **References** 鈥?寮曠敤鍒楄〃

---

## 10. 鐮旂┒鏂瑰悜寤鸿

鍒嗘瀽浣犵殑鐭ヨ瘑搴擄紝鎵惧嚭鐮旂┒绌虹櫧锛屽缓璁柊鏂瑰悜銆?
```bash
# 鍒嗘瀽骞剁粰鍑哄缓璁?paper-expert suggest "GAN-OPC"

# 涓嶅仛瓒嬪娍鍒嗘瀽锛堟洿蹇級
paper-expert suggest "mask optimization" --no-trends
```

杈撳嚭鍖呭惈锛?- **3-5 涓爺绌舵柟鍚戝缓璁?*锛屾瘡涓湁鏍囬銆佹弿杩般€佽瘉鎹€佹柊棰栧害璇勪及
- **瓒嬪娍鍒嗘瀽**锛氬摢浜涙柟娉曞湪涓婂崌/涓嬮檷
- **鏂规硶脳闂绌虹櫧鐭╅樀**锛氬摢浜涚粍鍚堣繕娌′汉鍋?
---

## 11. 棰嗗煙涓撳妯″紡

绯荤粺鎬ч槄璇绘煇鏂瑰悜鐨勬墍鏈夎鏂囷紝褰㈡垚缁撴瀯鍖栭鍩熺煡璇嗐€?
```bash
# 鏋勫缓棰嗗煙鐭ヨ瘑锛堥娆′娇鐢紝浼氶€愮瘒娑堝寲璁烘枃锛?paper-expert expert "inverse lithography technology"

# 鏄剧ず娑堝寲杩涘害
paper-expert expert "inverse lithography technology" --verbose

# 鏈夋柊璁烘枃鍚庯紝澧為噺鏇存柊锛堝彧娑堝寲鏂版坊鍔犵殑璁烘枃锛?paper-expert expert "inverse lithography technology" --update

# 浠ヤ笓瀹惰韩浠藉洖绛旈棶棰橈紙姣旀櫘閫?QA 鏇存湁娣卞害锛?paper-expert expert "ILT" --ask "What are the limitations of current neural ILT methods?"
```

鐭ヨ瘑鎶ュ憡鍖呭惈锛?1. **Concept Map** 鈥?鍏抽敭姒傚康鍙婂叧绯?2. **Method Evolution** 鈥?鏂规硶婕旇繘鏃堕棿绾?3. **Key Debates** 鈥?鏍稿績浜夎
4. **Landmark Papers** 鈥?閲岀▼纰戣鏂?5. **State of the Art** 鈥?褰撳墠鏈€浼樻柟娉曞強灞€闄?
---

## 12. 閰嶇疆鍙傝€?
閰嶇疆鏂囦欢浣嶇疆锛?- Windows: `%APPDATA%\paper_expert\config.toml`
- Mac/Linux: `~/.config/paper_expert/config.toml`

```bash
# 鏌ョ湅鎵€鏈夐厤缃?paper-expert config show

# 璁剧疆鍗曢」
paper-expert config set <key> <value>

# 鎭㈠榛樿
paper-expert config reset
```

### 甯哥敤閰嶇疆椤?
| 閰嶇疆椤?| 璇存槑 | 榛樿鍊?|
|--------|------|--------|
| `library_path` | 鐭ヨ瘑搴撳瓨鍌ㄨ矾寰?| `~/paper-expert-library` |
| `llm.cloud_model` | 浜戠 LLM 妯″瀷 | `openai/gpt-4o` |
| `llm.local_model` | 鏈湴 LLM锛堝垎绫荤敤锛?| `ollama/qwen2.5` |
| `llm.api_base` | API 浠ｇ悊鍦板潃 | 绌猴紙鐩磋繛 OpenAI锛?|
| `api_keys.openai` | OpenAI API Key | 绌?|
| `api_keys.semantic_scholar` | Semantic paper-expert Key锛堟彁楂樻悳绱㈤€熷害锛?| 绌?|
| `api_keys.unpaywall_email` | Unpaywall 閭锛堟彁楂?PDF 鑾峰彇鐜囷級 | 绌?|
| `search.default_sources` | 榛樿鎼滅储婧?| semantic_scholar, openalex |
| `parser.preferred` | PDF 瑙ｆ瀽鍣?| marker |

---

## 13. 甯歌闂

### Q: 鎼滅储寰堟參锛岀粡甯歌秴鏃讹紵

娌￠厤 Semantic paper-expert API key 鏃堕檺閫?1 娆?绉掋€傚厤璐圭敵璇蜂竴涓?key 鍙彁鍗囧埌 100 娆?绉掞細
```bash
paper-expert config set api_keys.semantic_paper-expert 浣犵殑S2key
```
鐢宠鍦板潃锛歨ttps://www.semanticscholar.org/product/api

### Q: 娣诲姞璁烘枃鏃?PDF 涓嬭浇涓嶅埌锛?
paper-expert 鍙€氳繃鍚堟硶鍏嶈垂娓犻亾鑾峰彇 PDF锛坅rXiv銆丱A 鐗堟湰锛夈€備粯璐规湡鍒婏紙IEEE銆丄CM锛夌殑璁烘枃浼氭爣璁颁负 `metadata-only`銆備綘鍙互锛?1. 閫氳繃瀛︽牎 VPN 鎵嬪姩涓嬭浇 PDF
2. 鏀惧埌涓€涓枃浠跺す閲?3. 杩愯 `paper-expert import 鏂囦欢澶硅矾寰?` 鑷姩鍖归厤鍏ュ簱

### Q: "QA requires a cloud LLM API key" 鎬庝箞鍔烇紵

QA銆佺患杩般€佷笓瀹舵ā寮忛渶瑕佷簯绔?LLM銆傞厤缃柟娉曪細
```bash
paper-expert config set api_keys.openai 浣犵殑APIkey
paper-expert config set llm.api_base 浣犵殑浠ｇ悊鍦板潃锛堝鏋滅敤绗笁鏂逛唬鐞嗭級
paper-expert config set llm.cloud_model openai/妯″瀷鍚?```

### Q: 鍒嗙被涓嶅噯纭紵

L0锛堝ぇ鏂瑰悜锛夌敤鍏抽敭璇嶈鍒欙紝瀵?AI/鍏夊埢棰嗗煙姣旇緝鍑嗙‘锛屽叾浠栭鍩熷彲鑳藉綊涓?"Other"銆備綘鍙互锛?- 鎵嬪姩鎵撴爣绛撅細`paper-expert lib tag 42 --add "鎴戠殑鏍囩"`
- 鎵╁睍璇嶈〃锛歚paper-expert lib vocab --add "鏂版湳璇? --aliases "鍒悕1, 鍒悕2"`

### Q: 鐭ヨ瘑搴撴枃浠跺瓨鍦ㄥ摢閲岋紵

```
~/paper-expert-library/           锛堝彲閫氳繃 config 淇敼璺緞锛?鈹溾攢鈹€ metadata.db              SQLite 鏁版嵁搴擄紙鎵€鏈夎鏂囧厓鏁版嵁锛?鈹溾攢鈹€ pdfs/                    PDF 鏂囦欢锛堟寜鍒嗙被瀛愭枃浠跺す瀛樻斁锛?鈹?  鈹溾攢鈹€ AI/
鈹?  鈹溾攢鈹€ Computational Lithography/
鈹?  鈹溾攢鈹€ Cross-domain/
鈹?  鈹斺攢鈹€ Bei Yu/              锛堣嚜瀹氫箟鏂囦欢澶癸級
鈹溾攢鈹€ vectors/                 鍚戦噺绱㈠紩锛堝彲閲嶅缓锛?鈹斺攢鈹€ parsed/                  瑙ｆ瀽鍚庢枃鏈紦瀛?```

### Q: 濡備綍澶囦唤锛?
澶囦唤 `~/paper-expert-library/` 鏁翠釜鏂囦欢澶瑰嵆鍙€傛渶閲嶈鐨勬槸 `metadata.db`锛堟墍鏈夊厓鏁版嵁鍜屾爣绛撅級鍜?`pdfs/`锛圥DF 鏂囦欢锛夈€俙vectors/` 鍙互閫氳繃 `paper-expert lib rebuild-index` 閲嶅缓銆?
---

## 蹇€熷弬鑰冨崱

```
paper-expert search <query>           鎼滅储璁烘枃
paper-expert add <id>                 娣诲姞鍗曠瘒
paper-expert import <path>            鎵归噺瀵煎叆锛圔ibTeX/鐩綍/Zotero锛?paper-expert lib list                 鍒楀嚭璁烘枃
paper-expert lib tag <id> --add <tag> 鎵撴爣绛?paper-expert lib stats                缁熻淇℃伅
paper-expert read <id>                鏌ョ湅璁烘枃
paper-expert ask <question>           鎻愰棶锛圦A锛?paper-expert review <topic>           鐢熸垚鏂囩尞缁艰堪
paper-expert suggest <topic>          鐮旂┒鏂瑰悜寤鸿
paper-expert expert <topic>           棰嗗煙涓撳妯″紡
paper-expert config show              鏌ョ湅閰嶇疆
```

