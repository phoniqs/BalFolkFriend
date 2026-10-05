# BalFolkFriend

**Reconnaissance de mélodies de bal folk** : joue ou chante quelques notes, BalFolkFriend cherche le morceau parmi \~4 100 partitions du répertoire balfolk (France, Bretagne, Belgique…).

*Identify balfolk tunes by playing or humming a few notes. About 4,100 tunes from the French-speaking balfolk repertoire.*

Application web : https://balfolkfriend.netlify.app *(à adapter)*

## Origine / Credits

* **Moteur de reconnaissance et application** : fork de **FolkFriend**. Le code d'origine, sa licence (fichier `LICENSE`) et ses crédits sont conservés ; seuls l'index, le logo et quelques écrans ont été modifiés.
* **Partitions** : issues de [Baloche](https://baloche.onth.org), qui référence des partitions de musique traditionnelle hébergées sur de nombreux sites (par exemple `lediato.free.fr`, `partitions.bzh`, `diatonalpartitions.fr`, `ligue-auvergnate.com`). Chaque morceau de l'application renvoie vers sa fiche Baloche par le bouton **Source** ; les compositeurs sont indiqués quand la fiche les donne. Les partitions de l'index ont été **converties automatiquement** (ABC direct, MIDI, MuseScore, reconnaissance optique des PDF) et peuvent contenir des erreurs : les conversions approximatives sont marquées `needs\_review` dans le corpus d'origine.

## Retrait d'un morceau / Takedown

Si vous êtes l'auteur ou l'ayant droit d'une partition et souhaitez qu'elle soit retirée de l'index : **arpagandekniga@gmail.com** . Merci d'indiquer le titre ou l'adresse de la fiche Baloche.

## Outils de fabrication de l'index (`baloche-tools/`)

Les scripts utilisés pour construire l'index (sans les partitions elles-mêmes) :

|Étape|Script|
|-|-|
|Téléchargement depuis Baloche (par style)|`baloche\_download.py`|
|Extraction des ABC embarqués dans des pages HTML|`extract\_abc.py`|
|Recadrage des PDF sur les portées de mélodie (supprime tablatures d'accordéon, ne garde que la mélodie des partitions multi-instruments)|`crop\_staves.py`|
|Conversion vers ABC (MIDI, MuseScore, Audiveris + xml2abc)|`baloche\_convert.py`|
|Nettoyage des ABC|`clean\_abc.py`|
|Construction de l'index de reconnaissance|`build\_index.py`, `abc\_to\_contour.py`|

Dépendances externes : Audiveris (avec ses données de langue Tesseract), MuseScore, `xml2abc.py`, `midi2abc`, PyMuPDF, Pillow, NumPy.

L'index (`app/public/res/folkfriend-non-user-data.json`) contient le texte ABC de chaque morceau, nécessaire à l'affichage et à l'écoute.

