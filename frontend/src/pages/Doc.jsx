/*
 * ============================================================================
 * Doc.jsx — la page « Comment ça marche » (adresse « /doc »)
 * ============================================================================
 *
 * RÔLE DE LA PAGE
 *   Expliquer ce que fait VRAIMENT l'application, ses limites et ses sources.
 *   Règle : chaque affirmation de cette page doit être vérifiable (code de
 *   l'appli ou source citée). Dernière relecture complète : 5 novembre 2026
 *   (voir docs/AUDIT.md). Si le traitement change côté serveur (seuils, durée
 *   des tranches, version de BatDetect2…), cette page doit être mise à jour.
 *
 * DONNÉES DEMANDÉES À L'API
 *   Aucune. C'est une page statique : tout le texte est écrit dans ce fichier.
 *   (Le seul lien vers le serveur est « /docs », qui ouvre la documentation
 *   technique de l'API générée par FastAPI.)
 *
 * SOMMAIRE DU FICHIER
 *   - H2, P, Code, A, Ul : petits composants de mise en forme réutilisés partout.
 *   - CHAIN        : les étapes du schéma « chaîne de traitement » (étiquettes + flèches).
 *   - STEPS        : les 6 étapes détaillées, numérotées.
 *   - READ         : l'explication des colonnes du tableau des cris.
 *   - JSON_SAMPLE  : un exemple de sortie brute de BatDetect2.
 *   - Doc          : la page elle-même (export par défaut), qui assemble tout ça.
 *
 * NOTIONS UTILES POUR LIRE CE FICHIER
 *   - Un « composant » React est une fonction qui renvoie ce qu'il faut afficher.
 *     Ce qui ressemble à du HTML (<p>, <b>…) s'appelle du JSX : une écriture
 *     transformée en JavaScript au moment de la compilation. On y écrit
 *     `className` au lieu de `class`, et on insère des valeurs entre accolades {…}.
 *   - Ce fichier n'importe rien : il n'utilise ni hook ni API. Le JSX y
 *     fonctionne sans `import React`, grâce à la compilation de Vite.
 *   - Les classes « text-xl font-bold mt-4… » sont des styles Tailwind (une
 *     classe = un petit style). Le préfixe `sm:` veut dire « à partir de 640 px
 *     de large ». `card` est un raccourci maison défini dans src/index.css.
 */

// --- Petits composants de mise en forme ---
// Déclarés en premier : les listes ci-dessous les utilisent.
// Ils évitent de répéter les mêmes classes Tailwind à chaque titre ou paragraphe.
// Chacun reçoit ses « props » (ses paramètres) dans un objet ; `{ children }`
// déstructure cet objet pour récupérer `children`, une prop spéciale de React :
// c'est tout ce qu'on écrit ENTRE la balise ouvrante et la balise fermante.
// Exemple : <P>Bonjour</P> → children vaut « Bonjour ».
// Ces composants sont écrits en « fonction fléchée » : `(paramètres) => résultat`.
//   - H2   : titre de section.
//   - P    : paragraphe, limité à environ 72 caractères de large (max-w-[72ch]) pour rester lisible.
//   - Code : mot technique en police à chasse fixe sur fond vert pâle (noms de champs, de fichiers).
//   - A    : lien externe. target="_blank" l'ouvre dans un nouvel onglet ;
//            rel="noreferrer" empêche la page ouverte d'agir sur la nôtre et
//            de savoir d'où vient le visiteur.
//   - Ul   : liste à puces (list-disc) avec un peu d'espace entre les points.
const H2 = ({ children }) => <h2 className="text-xl font-bold mt-4">{children}</h2>
const P = ({ children }) => <p className="max-w-[72ch] leading-relaxed">{children}</p>
const Code = ({ children }) => <code className="font-mono text-[0.85em] bg-green-soft px-1.5 py-px rounded-sm">{children}</code>
const A = ({ href, children }) => <a href={href} target="_blank" rel="noreferrer" className="text-green-dark underline underline-offset-2 hover:text-slate">{children}</a>
const Ul = ({ children }) => <ul className="list-disc pl-5 grid gap-2 text-sm leading-relaxed max-w-[75ch]">{children}</ul>

// --- Le schéma de la chaîne de traitement ---
// Chaque élément est un petit tableau [titre, sous-titre]. La page en fait une
// suite d'étiquettes reliées par des flèches. Le dernier élément est mis en
// valeur en vert (c'est le résultat final).
const CHAIN = [
  ['WAV', '250 ou 384 kHz'],
  ['Spectrogramme', 'image temps × fréquence'],
  ['BatDetect2', 'réseau de neurones'],
  ['Cris', 'début, fin, fréquences, espèce, score'],
  ['Contacts', 'tranches de 5 s'],
  ['Indices', 'contacts/h + groupes'],
  ['Comparaison', 'festival vs témoin, avant · pendant · après'],
]

// --- Les étapes détaillées ---
// Chaque étape est un tableau [titre, contenu]. Le contenu est du JSX entouré
// de <>…</> : c'est un « fragment », une enveloppe invisible qui permet de
// regrouper plusieurs morceaux (texte, <b>, <Code>…) sans ajouter de balise
// dans la page. On peut en effet ranger du JSX dans une constante, comme
// n'importe quelle autre valeur JavaScript.
// Le numéro de l'étape n'est pas écrit ici : il est calculé à l'affichage à
// partir de la position dans le tableau.
const STEPS = [
  ['Enregistrement', <>
    Un enregistreur autonome (AudioMoth le plus souvent) capte l’ultrason. Pour les chauves-souris, l’AudioMoth se règle à
    <b> 250 ou 384 kHz</b> (à 192 kHz on perd tout ce qui dépasse 96 kHz, dont le Petit rhinolophe). Il faut l’utiliser
    <b> en continu ou sur un horaire fixe</b>. En mode « déclenché » (fichiers <Code>…T.WAV</Code>), l’AudioMoth retire les
    silences : la durée du fichier n’est plus le temps d’écoute, et l’activité serait fausse. L’application refuse donc
    ces fichiers tant qu’ils n’ont pas été « dépliés » avec l’application AudioMoth (menu Fichier → Expand).
    <br /><b>Heure</b> : l’application lit l’heure ET le fuseau écrits dans le fichier par l’AudioMoth, et les convertit en
    heure française. Si le fichier ne les contient pas, elle prend l’heure du nom (<Code>20240712_213000.WAV</Code>) et la
    signale « fuseau non vérifié » : l’AudioMoth nomme ses fichiers en <b>UTC par défaut</b>, soit 2 h de moins que
    l’heure française en été.
  </>],
  ['Spectrogramme', <>
    Le son est découpé en fenêtres très courtes et converti en image temps × fréquence. C’est ce que voit le modèle, et
    c’est ce qu’un chiroptérologue lit à l’œil. La page de chaque fichier l’affiche de 0,5 à 5 secondes à la fois, avec
    les cadres des cris détectés. Le bouton « Écouter ×10 » rejoue l’extrait dix fois plus lentement pour l’entendre.
  </>],
  ['Détection par BatDetect2', <>
    Réseau de neurones open source (Mac Aodha et al., 2022), version 1.3.1. Pour chaque cri d’<b>écholocation</b> qu’il
    reconnaît, il renvoie une boîte (<Code>start_time</Code>, <Code>end_time</Code>, <Code>low_freq</Code>,
    <Code>high_freq</Code>), un score de détection <Code>det_prob</Code>, une espèce proposée <Code>class</Code> et son score
    <Code>class_prob</Code>. L’application garde les cris de score supérieur à 0,1 (pour pouvoir les vérifier) et
    <b> compte ceux de score supérieur à 0,3</b> : c’est la valeur des exemples de la documentation, que l’auteur décrit
    comme « un bon point de départ » à valider sur ses propres données. Le fichier est lu par blocs de 60 s et analysé par
    tranches de 3 s, exactement comme BatDetect2 (les tests vérifient que le résultat est identique), mais sans le
    charger entièrement en mémoire, pour supporter des nuits entières.
  </>],
  ['Regroupement en contacts', <>
    Une chauve-souris qui passe émet des dizaines de cris : un cri n’est pas une unité de mesure. Comme Vigie-Chiro, qui
    découpe les enregistrements en séquences de 5 secondes, l’application compte un <b>contact</b> par tranche de 5 s
    (depuis le début du fichier) contenant au moins un cri compté, toutes espèces confondues.
  </>],
  ['Indices', <>
    <b>Activité</b> = contacts divisés par la durée des fichiers, en contacts par heure. C’est juste si l’enregistreur a
    tourné en continu sur la même plage horaire chaque nuit. La synthèse présente <b>séparément</b> les sites du festival
    et le ou les sites témoins. <b>Groupes</b> = groupes acoustiques (Pipistrelles, Myotis, Noctules / Sérotines,
    Oreillards, Barbastelle, Rhinolophes) ayant au moins un cri compté. Le groupe est déduit de l’espèce proposée par le
    modèle : c’est une indication à faire confirmer, pas une identification.
  </>],
  ['Comparaison avant / pendant / après', <>
    Design <b>BACI</b> (Before-After-Control-Impact) : mêmes appareils, mêmes réglages, mêmes emplacements, et un site
    témoin hors festival enregistré aux mêmes dates. Un impact se lit quand l’activité des sites du festival change
    pendant le festival et pas celle du témoin. L’application donne des <b>chiffres descriptifs</b>, pas une preuve
    statistique : pour conclure, voir « Ce qu’il faut pour prouver un impact » plus bas.
  </>],
]

// --- Les colonnes du tableau des cris (page d'un enregistrement) ---
// [nom de la colonne, explication]. Affiché sous forme de liste de définitions (<dl>).
const READ = [
  ['Début, Fin', 'Position du cri dans le fichier, en secondes. Un cri de pipistrelle dure quelques millisecondes, un cri de Grand rhinolophe plusieurs dizaines.'],
  ['F. basse, F. haute', 'Bas et haut du cadre de détection, en kHz : à peu près l’étendue en fréquence du cri. Ce n’est pas la « fréquence caractéristique » des naturalistes (fréquence où le cri est le plus fort, ex. ~45 kHz pour la Pipistrelle commune).'],
  ['Espèce, Groupe', 'Espèce proposée par le modèle (parmi 17 espèces britanniques) et son groupe acoustique. On raisonne en groupe.'],
  ['Score cri', 'Score du modèle (0 à 1). Plus il est haut, plus le modèle est sûr que c’est un cri de chauve-souris. Ce n’est pas une probabilité (l’auteur le précise). Sous 0,5 (orange) : à vérifier à l’œil ou à l’oreille.'],
  ['Score espèce', 'Score de l’espèce proposée. À prendre avec beaucoup de recul : le modèle n’a pas été évalué sur des données françaises.'],
]

// --- Exemple de sortie brute de BatDetect2 ---
// Les backticks permettent d'écrire une chaîne sur plusieurs lignes en gardant
// les retours à la ligne. Elle est affichée telle quelle dans un <pre> (bloc
// qui respecte les espaces et les retours à la ligne).
const JSON_SAMPLE = `{
  "id": "20180627_215323-RHIFER-LR_0_0.5.wav",
  "duration": 0.5,
  "annotation": [
    { "start_time": 0.0245, "end_time": 0.066,
      "low_freq": 68437, "high_freq": 84254,
      "class": "Rhinolophus ferrumequinum",
      "det_prob": 0.407, "class_prob": 0.407,
      "event": "Echolocation" }
  ]
}`

// --- La page ---
// `export default` : c'est ce composant qu'App.jsx importe pour l'adresse /doc.
// La page est une suite de sections : un titre (H2) puis du texte, un schéma ou une liste.
export default function Doc() {
  return (
    // <article> : balise HTML pour un contenu autonome. `grid gap-4` empile les
    // blocs avec un espace régulier ; max-w-4xl limite la largeur sur grand écran.
    <article className="grid gap-4 max-w-4xl">
      {/* Section 1 : le but de la chaîne de traitement, en une phrase.
          (Dans le JSX, un commentaire s'écrit entre accolades comme celui-ci,
          sinon il serait affiché comme du texte.) */}
      <H2>Ce que fait la chaîne de traitement</H2>
      <P>
        Transformer des enregistrements ultrasons bruts en deux indicateurs comparables avant, pendant et après un festival,
        sur les sites du festival et sur un site témoin : l’<b>activité</b> (contacts par heure) et les <b>groupes
        d’espèces</b> présents.
      </P>

      {/* Schéma de la chaîne : des étiquettes reliées par des flèches, qui passent à la ligne sur petit écran.
          flex-wrap : quand la ligne est pleine, les étiquettes suivantes passent dessous.
          .map() transforme chaque élément de CHAIN en un bloc. La fonction reçoit
          ([t, s], i) : la déstructuration sort directement le titre `t` et le
          sous-titre `s`, et `i` est la position (0, 1, 2…).
          `key={t}` : React demande une clé unique pour chaque élément d'une liste,
          afin de les reconnaître d'un affichage à l'autre ; ici les titres sont uniques.
          Les classes sont assemblées dans un « template literal » (backticks + ${…}),
          et le ternaire `condition ? A : B` colore en vert le dernier bloc.
          `i < CHAIN.length - 1 && <span>→</span>` : rendu conditionnel, la flèche
          n'est ajoutée qu'entre deux blocs, pas après le dernier.
          aria-hidden : la flèche est décorative, les lecteurs d'écran l'ignorent. */}
      <div className="card p-4 flex flex-wrap items-stretch gap-2" aria-label="Schéma de la chaîne de traitement">
        {CHAIN.map(([t, s], i) => (
          <div key={t} className="flex items-center gap-2">
            <div className={`rounded-sm border px-3 py-2 text-center min-w-[7rem] ${i === CHAIN.length - 1 ? 'bg-green-soft border-green' : 'bg-surface border-line'}`}>
              <div className="font-medium text-sm">{t}</div>
              <div className="text-xs text-slate-light">{s}</div>
            </div>
            {i < CHAIN.length - 1 && <span className="text-green-dark font-bold" aria-hidden>→</span>}
          </div>
        ))}
      </div>

      {/* Section 2 : les étapes numérotées. Chaque carte est une petite grille à
          2 colonnes : la pastille du numéro à gauche (auto = juste la place
          nécessaire), le titre et le texte à droite (1fr = le reste).
          row-span-2 : la pastille occupe la hauteur des deux lignes (titre + texte).
          Le numéro affiché est i + 1, car les positions d'un tableau commencent à 0. */}
      <div className="grid gap-3">
        {STEPS.map(([title, body], i) => (
          <div key={title} className="card p-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
            <span className="w-8 h-8 rounded-full bg-green text-white font-bold grid place-items-center text-sm row-span-2">{i + 1}</span>
            <h3 className="font-medium mt-1">{title}</h3>
            <p className="text-sm leading-relaxed">{body}</p>
          </div>
        ))}
      </div>

      {/* Section 3 : comment lire les colonnes du tableau des cris.
          <dl> / <dt> / <dd> : liste de définitions HTML (terme / définition).
          Sur téléphone, terme et définition sont l'un sous l'autre ; à partir de
          sm: (640 px), ils sont sur 2 colonnes (sm:grid-cols-[auto_1fr]).
          La classe `contents` rend la <div> « transparente » pour la grille : ses
          enfants <dt> et <dd> se placent directement dans les colonnes de la <dl>.
          La <div> sert seulement à porter la `key` exigée par React. */}
      <H2>Lire le tableau des cris</H2>
      <dl className="card p-4 grid sm:grid-cols-[auto_1fr] gap-x-5 gap-y-2 text-sm">
        {READ.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="font-medium text-green-dark whitespace-nowrap mt-2 sm:mt-0">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>

      {/* Section 4 : les limites de la méthode, avec des liens vers les sources
          (composant A défini en haut du fichier : ouverture dans un nouvel onglet). */}
      <H2>Ce que la méthode ne peut pas faire</H2>
      <Ul>
        <li><b>Compter des individus.</b> Un micro ne distingue pas une pipistrelle qui passe 50 fois de 50 pipistrelles qui passent une fois. L’acoustique mesure une activité, jamais un effectif.</li>
        <li><b>Garantir que chaque cri est une chauve-souris.</b> L’auteur de BatDetect2 prévient que le modèle peut confondre insectes et bruits avec des chauves-souris, surtout loin de ses conditions d’entraînement (<A href="https://github.com/macaodha/batdetect2">FAQ du dépôt</A>, tickets <A href="https://github.com/macaodha/batdetect2/issues/48">#48</A> et <A href="https://github.com/macaodha/batdetect2/issues/50">#50</A>). En été, les sauterelles et grillons, et en festival le matériel électronique, sont des sources probables.</li>
        <li><b>Reconnaître les espèces françaises.</b> Le modèle a été entraîné au Royaume-Uni sur 17 espèces. Il ne connaît pas notamment la Pipistrelle de Kuhl, le Vespère de Savi, le Minioptère, le Molosse ou le Grand murin : leurs cris sont attribués à une espèce voisine, ou manqués. Nous n’avons trouvé aucune évaluation publiée de BatDetect2 sur des données françaises.</li>
        <li><b>Voir les cris sociaux et les phases de capture.</b> Le modèle n’a appris que les cris d’écholocation (tickets <A href="https://github.com/macaodha/batdetect2/issues/49">#49</A> et <A href="https://github.com/macaodha/batdetect2/issues/59">#59</A>).</li>
        <li><b>Donner des probabilités.</b> Les scores sont des niveaux de confiance, pas des probabilités, et le bon seuil dépend des espèces et des conditions (ticket <A href="https://github.com/macaodha/batdetect2/issues/46">#46</A>, <A href="https://github.com/macaodha/batdetect2/issues/72">#72</A>).</li>
        <li><b>Remplacer une relecture humaine.</b> Il faut vérifier à la main un échantillon de cris, dans chaque phase et sur chaque site, en particulier pendant le festival où le bruit est nouveau. À l’espèce, même les logiciels spécialisés se trompent beaucoup : de 31 à 77 % de bonnes réponses selon le logiciel dans Brabant et al. (2018).</li>
        <li><b>Tout capter.</b> Un enregistreur passif rate une partie des contacts (Barataud 2021). Ce qui compte, c’est de garder le même matériel et les mêmes réglages d’une phase et d’un site à l’autre.</li>
      </Ul>

      {/* Section 5 : ce qu'il faut en plus de l'application pour conclure à un impact. */}
      <H2>Ce qu’il faut pour prouver un impact</H2>
      <P>L’application fournit les données ; la preuve demande en plus :</P>
      <Ul>
        <li><b>Plusieurs nuits par phase</b> sur chaque site : l’activité varie beaucoup d’une nuit à l’autre (météo, insectes). Visez au moins 3 à 5 nuits par phase : Skalak et al. (2012) montrent que plusieurs nuits sont nécessaires même pour détecter les espèces communes.</li>
        <li><b>La même plage horaire chaque nuit</b>, par exemple du coucher du soleil − 30 min au lever + 30 min, comme le protocole <A href="https://www.vigienature.fr/fr/le-protocole-en-detail">Vigie-Chiro</A>, et la météo de chaque nuit (température, vent, pluie).</li>
        <li><b>Une analyse statistique</b> des contacts par nuit, avec la comparaison festival / témoin × avant / pendant (modèle de comptage, par exemple binomial négatif). L’effet du festival est l’interaction entre ces deux facteurs.</li>
        <li><b>Une analyse par groupe</b> : les effets diffèrent selon les groupes. Hooker et al. (2023), une étude publiée sur la musique de festival et les chauves-souris, trouvent une baisse d’activité pour les Noctules / Sérotines et la Pipistrelle commune, pas pour les Myotis (<A href="https://doi.org/10.1002/2688-8319.12250">Ecological Solutions and Evidence</A>).</li>
      </Ul>

      {/* Section 6 : la licence du modèle utilisé. */}
      <H2>Licence de BatDetect2</H2>
      <P>
        BatDetect2 (code et modèle) est publié sous licence <A href="https://github.com/macaodha/batdetect2/blob/main/LICENSE.md">Creative Commons BY-NC 4.0</A> :
        utilisation libre <b>à des fins non commerciales</b>, en citant les auteurs (Mac Aodha et al., 2022). Si l’étude d’impact
        est rémunérée (par exemple par l’organisateur du festival), il faut d’abord demander l’accord des auteurs.
      </P>

      {/* Section 7 : un exemple de sortie brute de BatDetect2 (constante JSON_SAMPLE).
          overflow-x-auto : si une ligne est trop longue, le bloc défile horizontalement
          au lieu de déborder de l'écran. */}
      <H2>Format de sortie (JSON BatDetect2)</H2>
      <P>Pour chaque fichier, BatDetect2 produit une liste de cris (scores arrondis à 3 décimales). L’application les range en base, une ligne par cri ; ce sont ces lignes qu’affiche le tableau.</P>
      <pre className="card p-4 overflow-x-auto text-xs leading-relaxed font-mono">{JSON_SAMPLE}</pre>

      {/* Section 8 : comment l'application est construite et où sont stockés les sons.
          Le dernier lien est un <a> classique (et non le composant A) : /docs est
          une page servie par le serveur FastAPI, on l'ouvre dans le même onglet. */}
      <H2>Architecture de l’application</H2>
      <Ul>
        <li><b>Serveur (backend)</b> : Python + FastAPI. Il reçoit les WAV, lance BatDetect2 en arrière-plan (un fichier à la fois), calcule contacts et groupes, dessine les spectrogrammes et range tout dans une base SQLite.</li>
        <li><b>Interface (frontend)</b> : React + Vite + Tailwind, aux couleurs de Lagom Natura, servie par le même serveur.</li>
        <li><b>Où sont les sons ?</b> Sur la machine qui fait tourner l’application : le PC en local, ou le serveur si elle est en ligne. La documentation technique de l’API est sur <a className="text-green-dark underline" href="/docs">/docs</a>.</li>
      </Ul>
    </article>
  )
}
