# Sut i ychwanegu alaw

Mae pob alaw yn Y Sesiwn yn un ffeil destun mewn
[nodiant ABC](https://abcnotation.com/): `tunes/<ffolder>/tune.abc` yn
[ystorfa GitHub](https://github.com/MarcoGorelli/y-sesiwn). Mae'r sgôr, y
chwarae a'r newid cywair i gyd yn cael eu gwneud o'r ffeil honno. I ychwanegu
alaw, rydych chi'n ysgrifennu ei ffeil ABC ac yn ei chynnig drwy *pull
request*. Unwaith y caiff ei derbyn, mae'r ap yn diweddaru ohono'i hun.

## 1. Ysgrifennu'r alaw mewn ABC

Dyma enghraifft gyflawn:

```
X:1
T:Llancesau Trefaldwyn
R:jig
M:6/8
L:1/8
K:D
AG |: F2 F GFG | AFD DFA | B2 c dcB | ABG FGE |
F2 F GFG | AFD DFA | Bgf edc |1 d3 dAG :|
[2 d3 dcd || e2 c Ace | f2 d Adf | gfe fed |
ecA Acd | e2 c Ace | f2 d Adf | efd cdB
|: ABG FGE | F2 F GFG | AFD DFA |1 B2 c dcB :|
[2 Bgf edc || d3 d |]
```

Y *pennawd* yw'r llinellau ar y dechrau:

| Llinell | Angen? | Beth yw hi |
|---|---|---|
| `X:1` | oes | `X:1` bob tro. |
| `T:` | oes | Y teitl, fel y mae ar y sgôr. |
| `R:` | argymhellir | Math o alaw, e.e. `jig`, `rîl`, `polca`, `walts`, `pibddawns`. Mae'n gosod y tempo arferol: jigiau 112, riliau 90, polcas 100, unrhyw beth arall 100 curiad y funud. |
| `M:` | oes | Amseriad, e.e. `6/8`, `4/4`, `3/4`. |
| `L:` | oes | Hyd arferol nodyn, fel arfer `1/8`. |
| `K:` | oes, **olaf** | Cywair, e.e. `D`, `Em`, `ADor`. Mae'r nodau'n dechrau ar y llinell nesaf. |
| `C:` | dewisol | Cyfansoddwr neu drefnydd. |
| rhagor o linellau `T:` | dewisol | Enwau eraill ar yr alaw; mae modd chwilio amdanyn nhw hefyd. |
| `B:`, `N:`, `O:`, `S:` | dewisol | Llyfr, nodiadau, man tarddiad, ffynhonnell. Yn cael eu dangos dan Manylion. |

Am deitlau:

- Defnyddiwch yr enw sydd ar y sgôr, heb gromfachau.
- Os oes alaw gyda'r un enw yn yr ap yn barod, galwch eich un chi
  `<Enw> (version 2)` (neu 3, 4, …). Mae pob fersiwn o alaw yn rhannu un
  dudalen, gyda thab i bob un; mae llinell `B:` (y llyfr y daw ohono) yn
  enwi eich tab chi.
- Mae llinellau tempo (`Q:`) yn cael eu hanwybyddu: llithrydd tempo'r ap sy'n
  penderfynu.

Mae cordiau'n ddewisol. Rhowch bob un mewn dyfynodau dwbl yn union cyn y
nodyn y mae'n dechrau arno (`"G"B2 G GFG | "D7"A2 A ABc |`), a dywedwch o ble
maen nhw'n dod mewn llinell `%%chords` yn y pennawd, e.e.
`%%chords From the Alawon Cymru score`. Mae tudalen yr alaw yn eu dangos fel
siart i gyfeilyddion, ym mha bynnag gywair a ddewisir.

Os ydych chi'n newydd i ABC, mae'r
[cyflwyniad i nodiant ABC](https://abcnotation.com/learn) (yn Saesneg) yn
esbonio'r nodau a'r barrau.

## 2. Gwirio ei bod yn edrych ac yn swnio'n iawn

Gludwch eich ABC i mewn i [abcjs Quick Editor](https://editor.drawthedots.com/).
Mae'n defnyddio'r un llyfrgell â'r Sesiwn, felly os yw'r sgôr yn edrych yn
iawn ac yn chwarae'n iawn yno, bydd yn yr ap hefyd.

## 3. Dewis enw'r ffolder

Mae'r ffolder wedi'i henwi ar ôl y teitl: llythrennau bach, heb acenion, a
chysylltnod yn lle unrhyw beth nad yw'n llythyren nac yn rhif.

| Teitl | Ffolder |
|---|---|
| Llancesau Trefaldwyn | `tunes/llancesau-trefaldwyn/` |
| Codi'r Hwyl | `tunes/codi-r-hwyl/` |
| Tŷ Coch Caerdydd (version 2) | `tunes/ty-coch-caerdydd-version-2/` |

## 4. Agor pull request

### Yn y porwr (heb osod dim)

1. Mewngofnodwch i GitHub ac agorwch
   [ystorfa'r Sesiwn](https://github.com/MarcoGorelli/y-sesiwn).
2. Cliciwch **Add file → Create new file**. Bydd GitHub yn cynnig gwneud eich
   copi eich hun (*fork*) yn gyntaf; derbyniwch.
3. Ym mlwch enw'r ffeil, teipiwch y llwybr llawn, e.e.
   `tunes/codi-r-hwyl/tune.abc`. Mae teipio `/` yn creu'r ffolderi.
4. Gludwch eich ABC i mewn i'r golygydd.
5. Cliciwch **Commit changes…**, yna **Propose changes**, yna
   **Create pull request**. Dywedwch yn y disgrifiad o ble daw'r alaw.

### Gyda git

```bash
git clone https://github.com/<your-username>/y-sesiwn.git   # after forking
cd y-sesiwn
git switch -c add-codi-r-hwyl
mkdir tunes/codi-r-hwyl
# write tunes/codi-r-hwyl/tune.abc
git add tunes/codi-r-hwyl/tune.abc
git commit -m "Add Codi'r Hwyl"
git push -u origin add-codi-r-hwyl
```

Yna agorwch y pull request o'ch fork ar GitHub.

I'w gweld yn yr ap cyn ei chynnig, rhedwch Y Sesiwn ar eich cyfrifiadur:

```bash
python build_site.py
python -m http.server -d _site 8000
```

ac agorwch http://localhost:8000.

## Beth sy'n digwydd nesaf

Mae eich pull request yn cael ei brofi'n awtomatig: mae GitHub yn gwirio bod
pob alaw (gan gynnwys eich un chi) yn dal i gael ei thynnu a'i chwarae, a bod
y wefan yn gweithio. Os yw gwiriad yn methu, mae'r pull request yn dweud pa un
a pham.

Mae'r cynhaliwr yn adolygu'r pull request ac efallai'n awgrymu newidiadau.
Unwaith y caiff ei gyfuno, mae'r [ap byw](https://ysesiwn.cymru/) yn
diweddaru ac mae'r alaw yn ymddangos wrth chwilio.

Dim ond `tune.abc` sydd ei angen: dim delwedd o'r sgôr na ffeil MIDI.

# Sut i gyflwyno cywiriadau

Wedi sylwi ar nodyn anghywir, teitl wedi'i gamsillafu, y cywair neu'r math
anghywir, neu'n gwybod pwy gyfansoddodd alaw? Mae dwy ffordd o'i gywiro.

## Dweud wrthym ni

[Ysgrifennwch aton ni](?page=contact), neu
[agorwch *issue*](https://github.com/MarcoGorelli/y-sesiwn/issues/new) ar
GitHub (bydd angen cyfrif GitHub am ddim arnoch chi). Dywedwch:

- pa alaw, gyda'i theitl fel y mae yn yr ap;
- beth sy'n anghywir a beth ddylai fod (er enghraifft "dylai bar 5 fod yn
  `B2 AB`", neu "dylai'r teitl fod yn *Y Gaseg Felen*");
- o ble daw'r fersiwn gywir, os ydych chi'n gwybod (llyfr, recordiad,
  gwefan).

## Ei gywiro eich hun gyda pull request

1. Dewch o hyd i ffeil yr alaw. Mae pob alaw yn `tunes/<ffolder>/tune.abc`,
   ac mae'r ffolder wedi'i henwi ar ôl y teitl (llythrennau bach, heb
   acenion, cysylltnodau rhwng geiriau), felly *Sawdl y Fuwch* yw
   `tunes/sawdl-y-fuwch/tune.abc`. Ar
   [dudalen yr ystorfa](https://github.com/MarcoGorelli/y-sesiwn), pwyswch `t`
   a theipiwch ran o'r enw i ddod o hyd iddi.
2. Agorwch y ffeil a chliciwch yr eicon pensil (**Edit this file**). Bydd
   GitHub yn cynnig gwneud eich copi eich hun (*fork*) yn gyntaf; derbyniwch.
3. Gwnewch eich newid. Mae'r nodau'n dilyn y llinell `K:`; mae'r llinellau
   pennawd uwch ei phen yn dal y teitl (`T:`), y math o alaw (`R:`), y cywair
   (`K:`) ac ati; gweler [Sut i ychwanegu alaw](?page=add) am ystyr pob
   llinell. Gallwch ychwanegu cyfansoddwr (`C:`) neu enw arall ar yr alaw
   (llinell `T:` ychwanegol). Gadewch y llinell `%%alawon ...` fel y mae.
4. Gludwch y ffeil gyfan i mewn i
   [abcjs Quick Editor](https://editor.drawthedots.com/) i wirio ei bod yn
   dal i edrych ac i chwarae'n iawn.
5. Cliciwch **Commit changes…**, yna **Propose changes**, yna
   **Create pull request**. Dywedwch beth wnaethoch chi ei newid a pham.

Os ydych chi'n newid y teitl `T:` cyntaf, dylai enw'r ffolder newid i'w
gyfateb. Gallwch wneud hynny yn yr un golygiad drwy newid y llwybr ym mlwch
enw'r ffeil (e.e. `tunes/old-name/tune.abc` i `tunes/new-name/tune.abc`), neu
ei grybwyll yn y pull request a bydd y cynhaliwr yn ei ailenwi.

Unwaith y caiff y pull request ei gyfuno, mae'r
[ap byw](https://ysesiwn.cymru/) yn dangos yr alaw wedi'i chywiro.
