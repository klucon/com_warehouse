# com_warehouse

Komponenta pro skladové hospodářství v ekosystému **KLUCON CMS**.

## Funkce

- materiálové karty včetně SKU, EAN, měrné jednotky a minimální zásoby,
- sklady a skladové pozice,
- stavby / zakázky jako odběrná místa,
- příjemky, výdejky a rezervace materiálu,
- neměnné skladové pohyby jako účetní pravda zásob,
- přehled aktuálních zásob a rezervací,
- základní šarže, expirace a pořizovací cena na položkách dokladů,
- administrační UI pro denní skladovou práci.
- vícepoložkové příjemky a výdejky,
- detail dokladu a storno opačným skladovým pohybem,
- skladová karta materiálu se stavy a historií pohybů.
- stavební rezervace jako plánovaná potřeba, která může přesáhnout aktuální sklad,
- přehled krytého a chybějícího množství k objednání.
- převodky mezi sklady,
- výdej materiálu přímo z rezervace.

## Datový model

```text
Warehouse
 └─ StockLocation

Material
 ├─ MaterialBatch
 ├─ StockLevel
 ├─ StockReservation
 └─ StockMovement

ConstructionProject
 ├─ Budget
 │   └─ BudgetItem
 ├─ StockReservation
 └─ StockDocument (issue)

StockDocument
 └─ StockDocumentItem
     └─ StockMovement
```

Aktuální stav zásob se drží v agregované tabulce `StockLevel`, ale zdrojem pravdy je
vždy append-only `StockMovement`. To umožňuje audit, inventury, šarže a reporty bez
pozdějšího přepisování historie.

## Admin rozhraní

Prefix: `/admin/com_warehouse`

| Sekce | URL |
|---|---|
| Dashboard | `/admin/com_warehouse` |
| Materiály | `/admin/com_warehouse/materials` |
| Sklady | `/admin/com_warehouse/warehouses` |
| Stavby | `/admin/com_warehouse/projects` |
| Příjem | `/admin/com_warehouse/receipts/new` |
| Výdej | `/admin/com_warehouse/issues/new` |
| Rezervace | `/admin/com_warehouse/reservations/new` |

## Instalace

Komponenta se instaluje standardní cestou KLUCON CMS marketplace. Databázové tabulky
vytváří `schema.upgrade_schema()`.

## GitHub release

Tag `vX.Y.Z` spustí workflow, které z `src/components/com_warehouse` vytvoří instalační
ZIP a `SHA256SUMS` pro marketplace.

## Verze

| Verze | Popis |
|---|---|
| 0.1.0 | Materiály, sklady, stavby, příjem, výdej, rezervace a audit pohybů |
| 0.1.1 | Vícepoložkové doklady, detail dokladu, storna a skladová karta materiálu |
| 0.1.2 | Převodky mezi sklady a výdej materiálu přímo z rezervace |
| 0.1.3 | Rezervace jako plánovaná potřeba stavby, záporné zásoby a chybějící množství |
| 0.1.4 | Drobečková navigace v adminu komponenty, roadmapa a publikace verze |
| 0.1.5 | SQL import materiálů a šarží, číselník MJ, rozpočty staveb a PDF doklady |
| 0.1.6 | Oprava SQL importu na aktualizovaných instalacích se starým unikátním EAN indexem |
| 0.1.7 | Stránkování materiálů a automatické hledání od 3 znaků |
| 0.1.8 | Výběr šarže v dokladu filtrovaný podle materiálu v řádku |
| 0.1.9 | Import materiálů a šarží z MATRIX.xlsx bez externí XLSX závislosti |

## Licence

MIT - (c) KLUCON
