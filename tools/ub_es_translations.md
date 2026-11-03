# Traducciones al español — Ultimatums, Boons & Refractions

Este archivo es la **fuente** de las traducciones al español de la comunidad (Rincón
Miskatonic) para la sección de Ultimatums, Boons & Refractions, mientras no haya traducción
oficial. Lo lee `tools/ub_es.py` y las inyecta en el grimoire español.

### Cómo rellenar

- Rellena SOLO los campos `ES-...:`. No toques los `##`, ni las líneas que empiezan por `>`
  (son la referencia en inglés, se ignoran).
- `ES-NOMBRE:` → el nombre de la carta en español, en la MISMA línea tras los dos puntos.
- `ES-TEXTO:` → el texto de reglas en español. Va en las líneas de DEBAJO (puede ocupar
  varias líneas y varios párrafos; separa párrafos con una línea en blanco). Termina en el
  siguiente `##` o al final del archivo.
- `ES-CAMPAÑA: Vástagos de la sangre` / `ESCENARIO:` (solo refracciones) → nombre en español de la campaña/escenario
  (p. ej. `Vástagos de la sangre`). En la misma línea.
- Una carta con `ES-NOMBRE` y `ES-TEXTO` vacíos se queda en inglés con su aviso. Puedes
  rellenar las que quieras e ir añadiendo poco a poco.

### Formato del texto (igual que el inglés de referencia)

- Iconos del juego: escríbelos entre corchetes, p. ej. `[perinvestigator]` (por investigador),
  `[blood]` (ficha de sangre, Vástagos de la sangre), `[combat]`, `[willpower]`, `[skull]`,
  `[cultist]`, `[autofail]`, `[eldersign]`, `[bless]`, `[curse]`… (los mismos tokens que ves en la
  referencia en inglés de cada carta).
- Negrita: `**texto**`. Cursiva: `*texto*`. Negrita+cursiva, para los **rasgos de carta**
  (p. ej. _Monster_, _Civilian_): `***texto***` o `**_texto_**` (las dos valen; en la referencia
  en inglés verás `**_Monster_**`).

Todas estas cartas se acreditarán como **traducidas por Rincón Miskatonic** (hasta que llegue
la traducción oficial). Si una carta la tradujo otra persona, añade una línea `ES-POR: Nombre`.

---

# Grimorio 1.1 (añadidas en el grimorio, aún sin español)

## ultimatum-of-malevolence

> **Ultimatum of Malevolence** · _Grimorio 1.1_
>
> Easy or Standard difficulty only. While playing, use the “Hard/Expert” side of the scenario reference card.

ES-NOMBRE: Ultimátum de malevolencia
ES-TEXTO: Solo para dificultades Fácil o Normal. Usa la cara “Difícil/Experto” de la carta de referencia de escenario durante la partida.

## ultimatum-of-the-spiral

> **Ultimatum of the Spiral** · _Grimorio 1.1_
>
> Campaign Mode only. After an investigator is defeated, add 1 random basic weakness to their deck.

ES-NOMBRE: Ultimátum de la espiral
ES-TEXTO: Sólo modo de campaña. Después de que un investigador sea derrotado, añade 1 debilidad básica aleatoria a su mazo.

## boon-of-nodens

> **Boon of Nodens** · _Grimorio 1.1_
>
> Hard or Expert difficulty only. While playing, use the “Easy/Standard” side of the scenario reference card.

ES-NOMBRE: Ayuda de Nodens
ES-TEXTO: Solo para dificultades Difícil o Experto. Usa la cara “Fácil/Normal” de la carta de referencia de escenario durante la partida.

## boon-of-persephone

> **Boon of Persephone** · _Grimorio 1.1_
>
> Campaign Mode only. If an investigator is defeated, they gain 3 additional experience.

ES-NOMBRE: Ayuda de Persephone
ES-TEXTO: Sólo modo de campaña. Si un investigador es derrotado, obtiene 3 de experiencia adicional.

## boon-of-the-morrigan

> **Boon of the Morrígan** · _Grimorio 1.1_
>
> When a player would add a random basic weakness to their deck during deckbuilding, they instead draw three random basic weaknesses, return one of their choice to the collection, and select one at random from the remaining two. The selected weakness is added to their deck.

ES-NOMBRE: Ayuda de Morrígan
ES-TEXTO: Cuando un jugador deba añadir una debilidad básica aleatoria a su mazo durante la construcción de mazo, en su lugar, roba 3 debilidades básicas aleatorias, devuelve 1 a su colección, a continuación, selecciona una aleatoria entre las dos restantes para añadirla a su mazo.

---

# Cultist Challenges 2026 (cartas fan)

## ultimatum-of-maddening-truth

> **Ultimatum of Maddening Truth** · _Cultist Challenges 2026_
>
> Each investigator that controls more than 1 [perinvestigator] clues gets –2 sanity.

ES-NOMBRE: Ultimátum de verdad enloquecedora
ES-TEXTO: Cada investigador que controle más de 1 pista [perinvestigator] recibe -2 de cordura.

## ultimatum-of-torment

> **Ultimatum of Torment** · _Cultist Challenges 2026_
>
> When you draw a signature weakness, reveal it and take 1 horror.

ES-NOMBRE: Ultimátum del tormento
ES-TEXTO: Después de robar una debilidad característica, revela la carta y recibe 1 punto de horror.

## ultimatum-of-nihilism

> **Ultimatum of Nihilism** · _Cultist Challenges 2026_
>
> Each time an investigator reveals, cancels, or ignores an autofail token, that investigator takes 1 damage or 1 horror.

ES-NOMBRE: Ultimátum de nihilismo
ES-TEXTO: Cada vez que un investigador revele, cancele o ignore una ficha de fallo automático: ese investigador debe recibir 1 punto de daño o 1 punto de horror.

## ultimatum-of-thin-blood

> **Ultimatum of Thin Blood** · _Cultist Challenges 2026_
>
> Whenever you seal a [blood] token on your investigator, also take a direct damage.
>
> Campaña (EN): Children of Blood

ES-NOMBRE: Ultimátum de la sangre débil
ES-CAMPAÑA: Vástagos de la sangre
ES-TEXTO: Después de sellar una ficha [blood] en tu investigador: recibe 1 punto de daño directo.

## ultimatum-of-regret

> **Ultimatum of Regret** · _Cultist Challenges 2026_
>
> Whenever a **_Civilian_** enemy is defeated, each investigator takes a direct horror and a mental trauma.
>
> Campaña (EN): Children of Blood

ES-NOMBRE: Ultimátum del arrepentimiento
ES-CAMPAÑA: Vástagos de la sangre
ES-TEXTO: Después de que un Enemigo **_Civil_** sea derrotado: cada investigador en juego sufre 1 punto de horror directo y 1 trauma mental.

## ultimatum-of-blood-frenzy

> **Ultimatum of Blood Frenzy (campaign)** · _Cultist Challenges 2026_
>
> The first time a **_Monster_** enemy attacks you each round, if you have a [blood] token sealed on your investigator: Release a [blood] token and the enemy attacks you an additional time.
>
> Campaña (EN): Children of Blood

ES-NOMBRE: Ultimátum del frenesí sangriento (campaña)
ES-CAMPAÑA: Vástagos de la sangre
ES-TEXTO: La primera vez que un Enemigo **_Monstruo_** te ataque en cada ronda, si tienes una ficha de [blood] sellada en tu investigador: Libera una ficha [blood] sellada y ese Enemigo te ataca una vez adicional.

## ultimatum-of-accursed-blood

> **Ultimatum of Accursed Blood** · _Cultist Challenges 2026_
>
> Treat the modifier of each revealed [blood] token as –2 instead of –1.
>
> Campaña (EN): Children of Blood

ES-NOMBRE: Ultimátum de sangre maldita
ES-CAMPAÑA: Vástagos de la sangre
ES-TEXTO: Trata el modificador de las fichas [blood] reveladas como –2 en lugar de –1.

## ultimatum-of-cold-blood

> **Ultimatum of Cold Blood** · _Cultist Challenges 2026_
>
> In addition to their normal effect, [blood] tokens gain the following effect: “If another [blood] token is revealed from the chaos bag during the same test, immediately end the ‘reveal chaos tokens’ step of the skill test and resolve the test as an automatic failure.”
>
> Campaña (EN): Children of Blood

ES-NOMBRE: Ultimátum de sangre fría
ES-CAMPAÑA: Vástagos de la sangre
ES-TEXTO: De forma adicional a sus efectos, las fichas [blood] obtienen el siguiente efecto: “Si es revelada otra ficha [blood] durante esta prueba, termina inmediatamente el paso ‘Revela la ficha de Caos’ y resuelva la prueba como si se hubiese revelado un fallo automático.”

## ultimatum-of-hostility

> **Ultimatum of Hostility** · _Cultist Challenges 2026_
>
> The residents of Arkham aren’t cooperative with the investigator’s attempts to keep them out of harm’s way. Based on the difficulty, replace one (Easy), two (Standard/Hard), or three (Expert) of the Waterfront Civilians with Bystanders from the Arkham Horror: The Card Game (2026) Core Set. When instructed to spawn a **_Civilian_**, draw one of the four civilians at random to spawn.
>
> Campaña (EN): Children of Blood · Escenario (EN): River of Blood

ES-NOMBRE: Ultimátum de la hostilidad
ES-CAMPAÑA: Vástagos de la sangre
ES-ESCENARIO: Río de sangre
ES-TEXTO: Los habitantes de Arkham no colaboran con los intentos del investigador de mantenerlos a salvo de los peligros. En base a la dificultad del juego, reemplaza un (Fácil), dos (Normal/Difícil) o tres (Experto) Enemigos Civil ribereño por Enemigos Transeúnte de la caja base de Arkham Horror: El juego de cartas (2026). Cuando se indique que debe aparecer un **_Civil_**, roba aleatoriamente uno de los cuatro Enemigos **_Civil_**.

## ultimatum-of-the-horde

> **Ultimatum of the Horde** · _Cultist Challenges 2026_
>
> Each copy of Child of Blood gains surge. During Setup, also gather the three copies of Child of Blood from the Blood Money encounter set.
>
> Campaña (EN): Children of Blood · Escenario (EN): New Horizons

ES-NOMBRE: Ultimátum de la horda
ES-CAMPAÑA: Vástagos de la sangre
ES-ESCENARIO: New Horizons
ES-TEXTO: Cada copia de Vástago de la sangre obtiene oleada. Durante la preparación, reúne también las tres copias de Vástagos de la sangre del conjunto de encuentros Dinero de sangre.

## ultimatum-of-blood-frenzy-blood-money

> **Ultimatum of Blood Frenzy (scenario)** · _Cultist Challenges 2026_
>
> While a **_Monster_** enemy is at their location, Suspicious Guests and Priscilla Thomas can not be parlayed with.
>
> Campaña (EN): Children of Blood · Escenario (EN): Blood Money

ES-NOMBRE: Ultimátum del frenesí sangriento (escenario)
ES-CAMPAÑA: Vástagos de la sangre
ES-ESCENARIO: Dinero de sangre
ES-TEXTO: Mientras un Enemigo **_Monstruo_** esté en su Lugar, no se puede Negociar con Priscilla Thomas ni con el Invitado sospechoso.
