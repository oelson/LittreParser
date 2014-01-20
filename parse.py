#-*- coding: utf-8 -*-

__all__ = ["parser", "entry"]

from textwrap import TextWrapper
import xml.etree.ElementTree as ET

from unidecode import unidecode
from LittreParser.error import EntryNotFound 

def _xml2dict(root):
    """
    Convert an XML node to a dictionnary.
    Recursive.
    """
    out = []
    for child in root.iterfind("./*"):
        out.append({
            "tag": child.tag,
            "text": child.text,
            "attrib": child.attrib,
            "children": _xml2dict(child)
        })
    return out


def _gettext(elem):
    """
    Équivalent DOM de la propriété "innerText"
    """
    return "".join(elem.itertext())


class parser:
    """
    Un parseur du dictionnaire XMLittré.
    """
    
    # piscine à parseur pour les 26 lettres de l'alphabet
    _ET_parsers = {}

    def __init__(self, xml_directory):
        self._xml_directory = xml_directory
    
    def load_xml_file(self, letter):
        """
        Le dictionnaire est subdivisé en 26 fichiers xml, nommés d'après les
        lettres de l'alphabet.
        Instancie un noeud Element à partir du contenu du fichier correspondant
        à la lettre et le range dans un dictionnaire.
        """
        if not isinstance(letter, str) or not len(letter) == 1:
            raise ValueError("need a letter from the alphabet")
        xml_path = "{}/{}.xml".format(
            self._xml_directory,
            letter
        )
        with open(xml_path, 'r') as xml_file:
            xml_content = xml_file.read()
            self._ET_parsers[letter] = ET.fromstring(xml_content)
    
    def get_parser(self, letter):
        """
        Obtient (éventuellement en l'instanciant à la volée) le bon parseur en
        fonction d'une lettre de l'alphabet.
        """
        letter = unidecode(letter.lower())
        if letter not in self._ET_parsers:
            self.load_xml_file(letter)
        return self._ET_parsers[letter]


    def get_entries(self, name):
        """
        Retourne une liste de noeuds XML <entry> correspondant au terme donné.
        Un terme peut correspondre à plusieurs entrées (sens multiples).
        TODO: récupérer une liste de mots proches en cas d'échec (mauvais accents, faute de frappe, etc...)
        """
        name = name.upper()
        # récupère le parseur adéquat
        p = self.get_parser(name[0])
        # Une entrée peut avoir plusieurs "sens" et par conséquent être
        # dupliquée
        entries = []
        for node in p.iterfind("./entree"):
            terme = node.attrib["terme"]
            # Cherche à établir une correspondance entre le masculin et le
            # féminin
            mal, fem = self.build_female(terme)
            if name == mal or name == fem:
                entries.append(node)
        if len(entries) == 0:
            raise EntryNotFound("the entry \"{}\" does not exist".format(name))
        return entries

    def build_female(self, word):
        """
        Construit le féminin d'un terme à partir de son masculin et de son
        suffixe féminin.
        """
        # extrait le radical (avec la marque du masculin) et le suffixe féminin
        values = word.split(",")
        rad = values[0].strip()
        # le terme est simple
        if len(values) == 1 or not values[1]:
            fem = ""
        # le terme est double
        else:
            fem_suffix = values[1].strip()
            # la première lettre du suffixe féminin doit
            # concorder avec celle du suffixe masculin
            first_fem_letter = fem_suffix[0]
            # extrait le radical brut (enlève le masculin)
            masc_pos = rad.rfind(first_fem_letter)
            prefix = rad[:masc_pos]
            # construit le féminin
            fem = prefix + fem_suffix
        return rad, fem

    def get_entries_as_dict(self,
                            name,
                            no_quotes=False,
                            no_synonyms=False,
                            no_history=False,
                            no_etymology=False):
        """
        Retourne les différents sens d'un mot sous la forme d'un dictionnaire
        dont les clés sont les indices de sens et les valeurs des entrées
        formattées sous forme d'arborescence.
        """
        name = name.upper()
        definition = {
            "terme": name,
            "sens": {}
        }
        for i, node in enumerate(self.get_entries(name)):
            e = entry(name, node)
            key = entry.get_sens_id() or i
            definition["sens"][key] = e.format_as_dict(
                no_quotes,
                no_synonyms,
                no_history,
                no_etymology
            )
        return definition


class entry:
    """
    Une entrée du dictionnaire générée par le parseur.
    Une entrée correspond à une définition.
    """

    def __init__(self, mot, entry):
        self.mot = mot
        self.entry = entry


    def get_sens_id(self):
        """
        Retourne l'indice de sens de la définition.
        """
        return int(self.entry.attrib.get("sens") or 1)


    def get_variante_text(self, v):
        """
        Retourne le texte définissant une variante.
        Ce texte s'étale éventuellement sur des noeuds collés à des morceaux
        de texte.
        """
        text = v.text.replace("\n", "") if v.text else ""
        # workaround: "find()" ne fonctionne pas, certainement à cause de
        # l'imbrication de noeuds texte et non-texte au sein d'un même
        # élément
        for sem in v.iter("semantique"):
            if sem.text:
                text += sem.text.replace("\n", "")
            if sem.tail:
                text += sem.tail.replace("\n", "")
        return text


    def get_variantes(self, corps_, no_quotes=False):
        """
        Retounre les variantes incluses dans le corps de l'entrée sous la forme
        d'un dictionnaire.
        """
        variantes = []
        for v_ in corps_.iter("variante"):
            variante = {
                "num": int(v_.attrib.get("num") or -1),
                "text": self.get_variante_text(v_),
                "indent": []
            }
            # adjoint les éventuelles citations propres à une variante
            if not no_quotes:
                variante["cit"] = self.get_citations(v_)
            # recherche les sous-parties
            for i_ in v_.iter("indent"):
                #subtext = _gettext(i_).rstrip()
                subtext = i_.text or ""
                subtext = subtext.rstrip()
                # wordaround
                for s_ in i_.iter("semantique"):
                    s_text = s_.text or ""
                    s_text = s_text.rstrip()
                    subtext += s_text
                # les sous-parties peuvent contenir des citations
                if not no_quotes:
                    citations = self.get_citations(i_)
                    variante["indent"].append({
                        "text": subtext,
                        "cit": citations
                    })
            variantes.append(variante)
        return variantes


    def get_citations(self, parent_):
        """
        Retounre les citations incluses dans un noeud sous la forme d'une liste
        de dictionnaires.
        """
        citations = []
        for c in parent_.iterfind("./cit"):
            citation = {
                "aut": c.attrib["aut"] or "aut. inc.",
                "ref": c.attrib["ref"] or "ref. inc.",
                "text": c.text
            }
            citations.append(citation)
        return citations


    def get_synonymes(self, entry_):
        """
        Retourne les synonymes d'une entrée sous la forme d'une liste.
        """
        synonymes = []
        for synonymes_ in entry_.iterfind("./rubrique[@nom='SYNONYME']"):
            for syn in synonymes_.iter("indent"):
                synonymes.append(syn.text.rstrip())
        return synonymes


    def get_historique(self, entry_):
        """
        Retounre l'historique d'une entrée sous la forme d'une liste de
        dictionnaires.
        """
        historique = []
        rubrique_ = entry_.find("./rubrique[@nom='HISTORIQUE']")
        if not rubrique_:
            return
        for indent in rubrique_.iter("indent"):
            # siècle
            date = indent.text.rstrip()
            # citations associées au siècle
            citations = self.get_citations(indent)
            historique.append({
                "date":date,
                "cit": citations
            })
        return historique


    def get_etymologie(self, entry_):
        """
        Retourne l'étymologie d'une entrée sous la forme d'une liste.
        """
        etymologies = []
        rubrique_ = entry_.find("./rubrique[@nom='ÉTYMOLOGIE']")
        for indent in rubrique_.iter("indent"):
            etymologies.append(_gettext(indent).rstrip())
        return etymologies


    def format_as_dict(self,
                       no_quotes=False,
                       no_synonyms=False,
                       no_history=False,
                       no_etymology=False):
        """
        Parcours l'entrée et la retourne sous la forme d'un dictionnaire.
        """
        entete_ = self.entry.find("./entete")
        corps_ = self.entry.find("./corps")
        prononciation_ = entete_.find("./prononciation")
        nature_ = entete_.find("./nature")

        e = {
            "entete": {
                "prononciation": prononciation_.text,
                "nature": nature_.text
            }
        }

        # Variantes
        variantes = self.get_variantes(corps_, no_quotes)
        if variantes:
            e["variantes"] = variantes

        # Synonymes
        if not no_synonyms:
            synonymes = self.get_synonymes(self.entry)
            if synonymes:
                e["synonymes"] = synonymes

        # Historique
        if not no_history:
            historique = self.get_historique(self.entry)
            if historique:
                e["historique"] = historique

        # Étymologie
        if not no_etymology:
            etymologies = self.get_etymologie(self.entry)
            if etymologies:
                e["etymologie"] = etymologies
        
        return e


class entry_formatter:
    """
    Classe de formattage d'une entrée.
    Les formats supportés sont:
        * le texte simple
        * le HTML
    """

    # Éléments de formattage en texte simple
    _nbsp = u"\u00A0"
    _bullet = u"\u2219\u25E6"
    _q = u"\u201C\u201D"

    # Séparateur de parties de la définition
    _subpart_separator = "\u2015"*24

    # Format de citation
    _citation_format = "{} ({}): "+_q[0]+"{}"+_q[1]

    # Nombre d'espace par niveau d'indentation
    _indent_factor = 2

    # Découpage propre du texte
    _display_width = 78


    def __init__(self, entries, fit_text=True):
        self.entries = entries
        self.fit_text = fit_text
        self.tw = TextWrapper(
            width=self._display_width,
            # l'indentation initiale sera toujours générée par /list_item/
            initial_indent = ""
        )


    def fill(self, text, subsequent_indent=0):
        """
        Retourne le texte passé en paramètre coupé au mot près à la largeur
        définie comme constante /_display_width/.
        Le paramètre /subsequent_indent/ est la taille du préfixe du texte,
        typiquement la taille de la liste à puce (espaces préc. compris).
        """
        self.tw.subsequent_indent = self._nbsp*subsequent_indent
        return self.tw.fill(text)


    def list_item(self, level=2, li_type=0, li_count=-1):
        """
        Formatte un élement de liste à puce.
        Si /li_type/ vaut -1, alors la liste est numérique et la puce aura pour
        valeur la variable /li_count/.
        """
        if li_type == -1:
            # l'item de liste est un nombre
            bullet = str(li_count)+"."
        else:
            # l'item de liste est une "puce"
            bullet = self._bullet[li_type]
        return self._nbsp * level * self._indent_factor + bullet + self._nbsp

    
    def format_entete(self, entete):
        """
        Formatte une entête de définition en texte simple.
        """
        text = "PRONONCIATION: '{}'\nNATURE: {}".format(
            entete["prononciation"],
            entete["nature"]
        )
        return text


    def format_citation(self, cit, level=0, li_style=0):
        """
        Formatte une citation en texte simple.
        """
        li = self.list_item(level, li_style)
        cit = self._citation_format.format(
            cit["aut"],
            cit["ref"],
            cit["text"]
        )
        text = li + cit
        # Coupe le texte proprement si il dépasse
        if self.fit_text:
            text = self.fill(text, len(li))
        return text + "\n"


    def format_variantes(self, variantes, base_indent_level=1):
        """
        Formatte les variantes en texte simple.
        """
        paragraph = ""
        for li_count, v_ in enumerate(variantes):
            # Construit un item de liste numérique
            if v_["num"] == -1:
                li_index = li_count+1
            else:
                li_index = v_["num"]
            li = self.list_item(base_indent_level, -1, li_index)
            text = li + v_["text"]
            # Coupe le texte proprement si il dépasse
            if self.fit_text:
                text = self.fill(text, len(li))
            text +=  "\n"
            # Adjoint les éventuelles citations
            if "cit" in v_:
                for c_ in v_["cit"]:
                    text += self.format_citation(c_, base_indent_level+1, 0)
            # Adjoint les éventuelles sous-parties
            for ind in v_["indent"]:
                li = self.list_item(base_indent_level+1, 0)
                _text = li + ind["text"]
                # Coupe le texte proprement si il dépasse
                if self.fit_text:
                    _text = self.fill(_text, len(li))
                text += _text + "\n"
                # citations liées à la sous-partie
                for cit in ind["cit"]:
                    text += self.format_citation(cit, base_indent_level+2, 1)
            paragraph += text
        return paragraph


    def format_synonymes(self, synonymes, base_indent_level=1):
        """
        Formatte une liste de synonymes en texte simple.
        """
        paragraph = ""
        for syn in synonymes:
            li = self.list_item(base_indent_level, 1)
            text = li + syn
            # Coupe le texte proprement si il dépasse
            if self.fit_text:
                text = self.fill(text, len(li))
            paragraph += text + "\n"
        return paragraph


    def format_historique(self, historique, base_indent_level=1):
        """
        Formatte une historique de définition en texte simple.
        """
        paragraph = ""
        for his in historique:
            li = self.list_item(base_indent_level, 0)
            text = li + his["date"]
            # Coupe le texte proprement si il dépasse
            if self.fit_text:
                text = self.fill(text, len(li))
            text += "\n"
            for cit in his["cit"]:
                text += self.format_citation(cit, base_indent_level+1, 1)
            paragraph += text
        return paragraph


    def format_etymologies(self, etymologie, base_indent_level=1):
        """
        Formatte une liste d'étymologie en texte simple.
        """
        paragraph = ""
        for ety in etymologie:
            li = self.list_item(base_indent_level, 0)
            text = li + ety
            # Coupe le texte proprement si il dépasse
            if self.fit_text:
                text = self.fill(text, len(li))
            paragraph += text + "\n"
        return paragraph


    def format(self):
        """
        Formatte l'entrée en texte simple.
        """
        text = "TERME: {}\n".format(self.entries["terme"])
        # les différents sens d'une entrée sont indexés par un indice numérique
        if len(self.entries["sens"]) == 1:
            initial_indent_level = 0
            print_sens_separator = False
        else:
            initial_indent_level = 1
            print_sens_separator = True

        for sens_id, definition in self.entries["sens"].items():
            if print_sens_separator:
                text += "{}\nSENS #{}\n".format(
                    self._subpart_separator,
                    sens_id
                )
            # Variantes du terme
            if "variantes" in definition:
                text += "\nVARIANTES:\n"
                text += self.format_variantes(
                    definition["variantes"],
                    initial_indent_level
                )
            # Synonymes
            if "synonymes" in definition:
                text += "\nSYNONYMES:\n"
                text += self.format_synonymes(
                    definition["synonymes"],
                    initial_indent_level
                )
            # Historique
            if "historique" in definition:
                text += "\nHISTORIQUE:\n"
                text += self.format_historique(
                    definition["historique"],
                    initial_indent_level
                )
            # Étymologie
            if "etymologie" in definition:
                text += "\nÉTYMOLOGIE:\n"
                text += self.format_etymologies(
                    definition["etymologie"],
                    initial_indent_level
                )

        return text


    def __repr__(self):
        return self.__str__()


    def __str__(self):
        return str(self.format())
