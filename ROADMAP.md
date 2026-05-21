# ROADMAP - com_warehouse

Tento dokument popisuje další vývoj komponenty `com_warehouse` pro KLUCON CMS.  
Záměr je držet skladové hospodářství jako nástroj pro stavební firmu, ne jako klasický e-shop.

## Hotovo

- materiálové karty se SKU, EAN, MJ, cenou a minimální zásobou,
- sklady a skladové pozice,
- stavby jako odběrná místa,
- příjemky, výdejky, převodky a rezervace,
- výdej z rezervace,
- záporné zásoby tam, kde to provoz dává smysl,
- skladová karta s pohyby,
- detail dokladu a storna,
- drobečková navigace v rámci komponenty,
- základní lokalizace `cs_CZ` a `en_GB`.

## Další krok

### 0.1.4 - Stabilizace jádra

- doplnit chybějící validační hlášky a sjednotit texty v administraci,
- doladit navigaci a formuláře v adminu,
- doplnit filtry a rychlé přehledy pro běžnou skladovou práci,
- zkontrolovat konzistenci názvosloví mezi sklady, stavbami a rezervacemi,
- doplnit testy pro hraniční stavy rezervací a výdeje.

### 0.2.0 - Plánování materiálu

- rezervace rozšířit o plánované datum potřeby a pořadí priority,
- zobrazovat, kolik je rezervace kryto skladem a kolik chybí k objednání,
- navrhovat nákup podle rezervací a minimálních zásob,
- přidat přehled materiálů, které je potřeba objednat v horizontu 7 až 14 dnů,
- připravit vazbu na nákupní doklady nebo export objednávkového seznamu.

### 0.3.0 - Profesionální sklad

- šarže a expirace jako plnohodnotná součást výdeje a příjmu,
- podpora více skladových pozic na jednu materiálovou kartu,
- inventury a korekční pohyby,
- lepší práce s cenami, pořizovací cenou a oceněním zásob,
- exporty do CSV/XLSX pro účetnictví a provoz.

### 1.0.0 - Provozní verze

- zpevnění oprávnění a přístupových rolí,
- auditní stopa nad důležitými operacemi,
- výkonové ladění pro větší objemy pohybů a dokladů,
- finální dokumentace pro administrátory,
- stabilní release workflow přes GitHub.

## Poznámka k prioritám

Priorita je dodržet provoz stavební firmy:

1. rezervace vzniká dopředu,
2. sklad může být i v mínusu,
3. systém musí ukázat, co je kryté a co se musí objednat,
4. teprve potom má smysl řešit rozšířenou evidenci šarží, cen a inventur.

