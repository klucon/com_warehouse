# com_warehouse

Komponenta pro skladové hospodářství v ekosystému **KLUCON CMS**.

## Funkce ve verzi 0.1.0

- materiálové karty včetně SKU, EAN, měrné jednotky a minimální zásoby,
- sklady a skladové pozice,
- stavby / zakázky jako odběrná místa,
- příjemky, výdejky a rezervace materiálu,
- neměnné skladové pohyby jako účetní pravda zásob,
- přehled aktuálních zásob a rezervací,
- základní šarže, expirace a pořizovací cena na položkách dokladů,
- administrační UI pro denní skladovou práci.

## Datový model

```text
Warehouse
 └─ StockLocation

Material
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

## Licence

MIT - (c) KLUCON
