# ROADMAP - com_warehouse

Tento dokument popisuje další vývoj komponenty `com_warehouse` pro KLUCON CMS.
Záměr je držet skladové hospodářství jako nástroj pro stavební firmu, ne jako
klasický e-shop.

## Hotovo

### Skladové jádro

- materiálové karty se SKU, EAN, MJ, cenou, minimální zásobou a stavem,
- sklady a skladové pozice spravované v administraci,
- příjemky, výdejky, převodky a rezervace,
- výdej z rezervace,
- záporné zásoby tam, kde to provoz dává smysl,
- skladová karta materiálu se stavy a historií pohybů,
- detail dokladu a storno dokladu opačným skladovým pohybem,
- automatické časové číslování dokladů ve formátu `RRRRMMDDHHmm01`, pokud
  uživatel nezadá číslo ručně.

### Materiály a import

- číselník měrných jednotek `com_warehouse_units`,
- vazba materiálu na `unit_id`,
- zachovaná textová MJ na materiálu kvůli zpětné kompatibilitě,
- stránkovaný přehled materiálů,
- automatické hledání materiálů od 3 znaků,
- samostatná evidence šarží materiálu v `com_warehouse_material_batches`,
- import materiálů z uživatelem nahraného SQL souboru,
- import materiálů a šarží z uživatelem nahraného `MATRIX.xlsx`,
- normalizace MJ při importu,
- import šarží ze sloupce `Sarze` při SQL importu,
- duplicitní materiály podle katalogového/SAP čísla se při importu neduplikují,
- duplicitní šarže se u stejného materiálu neduplikují,
- složka `soubory/` je vedená jako lokální pracovní podklad a je v `.gitignore`.

### Stavby a rozpočty

- stavby jako odběrná místa,
- provozní údaje stavby:
  - číslo stavby v EGD-Montáže,
  - číslo stavby,
  - odvolávka,
  - VZ,
  - parták,
  - odpovědný technik EGD,
- směry stavby spravované v administraci,
- podkapitoly směrů spravované ručně v administraci,
- rozpočtové položky umí nést vazbu na podkapitolu směru,
- administrace rozpočtů u stavby,
- ruční zadání rozpočtových položek u stavby,
- bilance stavby porovnává rozpočtované a vydané množství.

### Doklady a tisk

- tiskový/PDF náhled příjemek a výdejek v samostatném okně,
- tisk probíhá přes prohlížeč uživatele a lokální tiskárnu, ne přes server,
- PDF soubor lze stáhnout z náhledu dokladu,
- šarže z položek dokladu se propisuje do tiskového/PDF výstupu,
- PDF popisky jsou napojené na lokalizaci, nejsou natvrdo v generátoru.

### Technický stav

- drobečková navigace v rámci komponenty,
- základní lokalizace `cs_CZ` a `en_GB`,
- schema upgrade doplňuje nové sloupce pro existující instalace,
- release workflow vytváří instalační ZIP balíček a `SHA256SUMS` pro GitHub release,
- release workflow používá aktuální major verze GitHub Actions,
- testy pokrývají doklady, rezervace, převodky, import materiálu, PDF generování,
  stavby, směry, podkapitoly, rozpočtové položky a bilanci.

## Rozpracováno / omezení

- Šarže se ukládají do samostatné tabulky a umí vzniknout z SQL importu i z
  dokladu, ale ještě nejsou dotažené pro inventuru a výběr přesně podle
  zvoleného materiálu v řádku dokladu.
- Bilance stavby zatím počítá rozpočet proti skutečným výdejům; požadavky na
  materiál a rezervace v ní ještě nejsou zahrnuté.
- Rozpočty lze zadávat ručně, ale import z dodaných souborů `Rozp_*.xls` ještě
  není hotový.
- PDF výstup je funkční základ, ale ještě není dotažený přesně podle Word vzorů
  dodacího listu a požadavku materiálu.
- Číselník MJ existuje v databázi, ale ještě nemá vlastní plnou administrační
  obrazovku.

## Další krok

### 0.1.11 - Dokončení šarží kabelů a bubnů

Nejbližší priorita je dokončit práci se šaržemi kabelů/bubnů v uživatelském
rozhraní a importech.

Důvod:

- materiál už je importovatelný jako unikátní karta podle katalogového/SAP čísla,
- duplicitní řádky v SQL/MATRIX vznikají hlavně kvůli šaržím,
- šarže se nesmí ukládat do materiálové karty, protože budou průběžně přibývat,
- výdej kabelu musí umět nést konkrétní šarži/buben a vytisknout ji na doklad.

Už hotovo:

- tabulka `com_warehouse_material_batches`,
- uložení materiálu, čísla šarže/bubnu, stavu, poznámky a data posledního použití,
- unikátnost šarže v rámci materiálu,
- SQL import šarží ze sloupce `Sarze`,
- XLSX import materiálů a šarží z listu 10 v `MATRIX.xlsx`,
- základní administrace šarží u materiálu,
- editace poznámek a archivace šarží u materiálu,
- automatické založení nové šarže z příjmu/výdeje,
- výběr šarže v dokladu filtrovaný podle materiálu v konkrétním řádku,
- propsání šarže do PDF/tiskového náhledu dokladu.

Chybí dodělat:

1. doplnit historii použití konkrétní šarže/bubnu,
2. připravit inventurní pohled po šaržích.

## Backlog

### Materiály a číselníky

- doplnit plnou administraci číselníku měrných jednotek,
- doplnit přehled importních chyb a duplicit po dávce,
- potvrdit, které pole má být v systému uložené jako externí SAP ID:
  - v dodacím listu a požadavku je `ID` popsáno jako SAPové číslo EGD,
  - v SQL exportu vypadá `ID` jako pořadové číslo,
  - `kat_cislo` vypadá jako skutečné SAP/katalogové číslo.

### Stavby, rozpočty a bilance

- rozšířit editaci směrů a podkapitol o plnou správu, nejen založení,
- zvážit volitelnou šablonu podkapitol pro konkrétní provoz, spravovanou v adminu,
- připravit import rozpočtů ze souborů `Rozp_*.xls`, i když jsou určeny pro
  člověka a ne pro strojové čtení,
- umožnit kopírování položek rozpočtu do směru/podkapitoly,
- rozšířit bilanci stavby o požadavky na materiál,
- rozšířit bilanci stavby o rezervace,
- nezpracovávat poslední cenové sloupce z dodaných rozpočtů.

### Žádanky, dodací listy a plánování

- vytvořit žádanky materiálu vázané na konkrétní stavbu, směr a případně
  podkapitolu,
- umožnit žádanky interním lidem i subdodavatelům podle oprávnění,
- podporovat cílové místo přípravy materiálu, např. kóje, regál nebo stavba,
- rezervace rozšířit o plánované datum potřeby a pořadí priority,
- zobrazovat, kolik je požadavek kryt skladem a kolik chybí k objednání,
- navrhovat nákup podle žádanek, rezervací a minimálních zásob,
- přidat přehled materiálů, které je potřeba objednat v horizontu 7 až 14 dnů,
- generovat požadavek materiálu podle vzoru `Požadavek_materiálu_EF.docx`,
- generovat dodací list podle vzoru `Dodací_List_XX_EF.docx`,
- pro dodací list potvrdit, zda má používat stejné časové číslování jako skladový
  doklad,
- číslo požadavku může být jednodušší časové číslo,
- u dodacího listu evidovat a tisknout termín vrácení obalů; výchozí hodnota
  může být datum vystavení plus 3 měsíce, s možností ruční volby kalendářem.

### Profesionální sklad

- šarže a expirace jako plnohodnotná součást výdeje a příjmu,
- pokročilá práce se šaržemi:
  - inventura po šaržích,
  - historie použití,
  - uzavírání neaktivních šarží,
- podpora více skladových pozic na jednu materiálovou kartu,
- inventury a korekční pohyby,
- lepší práce s cenami, pořizovací cenou a oceněním zásob,
- exporty do CSV/XLSX pro účetnictví a provoz,
- ruční nebo poloautomatické zadání aktuálních skladových zásob z PDF exportů
  extranetu, protože extranet neumí export do Excelu ani CSV.

### Provozní verze

- zpevnění oprávnění a přístupových rolí,
- auditní stopa nad důležitými operacemi,
- výkonové ladění pro větší objemy pohybů a dokladů,
- finální dokumentace pro administrátory,
- dokumentace provozního release procesu.

## Vstupní podklady

Ve složce `soubory/` jsou pracovní podklady pro další vývoj. Složka je lokální a
nejde do commitu.

- `egdm-sklad.sql` - export tabulky `material` se sloupci `ID`, `kat_cislo`,
  `Nazev_Popis`, `Sarze`, `MJ`,
- `MATRIX.xlsx` - zdrojový seznam materiálu; list 10 obsahuje vše pohromadě,
  list 8 ostatní materiál a list 9 kabely a bubny,
- soubory `Rozp_*.xls` - příklady rozpočtů staveb určené pro import bilance stavby,
- `Dodací_List_XX_EF.docx` a `Požadavek_materiálu_EF.docx` - vzory výstupních dokladů.

## Poznámka k prioritám

Priorita je dodržet provoz stavební firmy:

1. rezervace vzniká dopředu,
2. sklad může být i v mínusu,
3. systém musí ukázat, co je kryté a co se musí objednat,
4. šarže kabelů/bubnů musí být oddělené od materiálové karty,
5. teprve potom má smysl řešit rozšířenou evidenci cen, inventur a exportů.
