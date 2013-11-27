#-*- coding: utf-8 -*-

__all__ = ["parser", "entry"]

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
        Retourne un itérateur d'éléments de la classe "entry" correspondant au
        mot passé en argument.
        TODO: récupérer une liste de mots proches en cas d'échec (mauvais accents, faute de frappe, etc...)
        """
        # récupère le parseur adéquat
        name = name.upper()
        letter = name[0]
        p = self.get_parser(letter)
        # Une entrée peut avoir plusieurs "sens" et par conséquent être
        # dupliquée
        for node in p.iterfind("./entree[@terme='{}']".format(name)):
            if node is None:
                raise EntryNotFound("the entry \"{}\" does not exist".format(name))
            yield entry(name, node)


class entry:
    """
    Une entrée du dictionnaire générée par le parseur.
    Une entrée correspond à une définition.
    """
    FORMAT_TYPE_PLAINTEXT = 0
    FORMAT_TYPE_HTML      = 1
    
    # Éléments de formattage en texte simple
    _nbsp = u"\u00A0"
    _bullet = u"\u2219\u25E6"
    _q = u"\u201C\u201D"

    # Séparateur de parties de la définition
    _subpart_separator = "\u2015"*10+"\n"

    def __init__(self, mot, entry):
        self.mot = mot
        self.entry = entry


    def __dict__(self):
        """
        Retourne la description de l'objet sous la forme d'un dictionnaire.
        """
        return _xml2dict(self.entry)


    def list_item_plaintext(self, indent=2, li_type=0, li_count=-1):
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
        return self._nbsp * indent + bullet + self._nbsp


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
                subtext = _gettext(i_).rstrip()
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
                "text": self._q[0]+c.text+self._q[1]
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


    def format(self,
               format_type=FORMAT_TYPE_PLAINTEXT,
               no_quotes=False,
               no_synonyms=False,
               no_history=False,
               no_etymology=False):
        """
        Formatte l'entrée selon l'argument "format_type":
          * en texte simple
          * en HTML
        """
        if format_type == self.FORMAT_TYPE_PLAINTEXT:
            text = self.format_plaintext(
                no_quotes,
                no_synonyms,
                no_history,
                no_etymology
            )
        elif format_type == self.FORMAT_TYPE_HTML:
            text = self.format_html()
        else:
            raise ValueError
        # supprime la nouvelle ligne de fin
        return text[0:-1]

    
    def format_citation_plaintext(self, cit, level=0, li_style=0):
        """
        Formatte une citation en texte simple.
        """
        li = self.list_item_plaintext(level, li_style)
        li += "{} ({}): {}\n".format(
            cit["aut"],
            cit["ref"],
            cit["text"]
        )
        return li


    def format_variantes_plaintext(self, variantes):
        """
        Formatte les variantes en texte simple.
        """
        text = "Variantes:\n"
        for (li_count, v_) in enumerate(variantes):
            # Construit un item de liste numérique
            if v_["num"] == -1:
                li_index = li_count+1
            else:
                li_index = v_["num"]
            v = self.list_item_plaintext(
                2,
                -1,
                li_index
            )
            v += v_["text"] + "\n"
            # Adjoint les éventuelles citations
            if "cit" in v_:
                for c_ in v_["cit"]:
                    v += self.format_citation_plaintext(c_, 4, 0)
            # Adjoint les éventuelles sous-parties
            for i_ in v_["indent"]:
                v += self.list_item_plaintext(4, 0) + "{}\n".format(
                    i_["text"]
                )
                # citations liées à la sous-partie
                for c_ in i_["cit"]:
                    v += self.format_citation_plaintext(c_, 6, 1)
            text += v
        return text


    def format_synonymes_plaintext(self, synonymes):
        """
        Formatte une liste de synonymes en texte simple.
        """
        text = "Synonymes:\n"
        for s_ in synonymes:
            text += self.list_item_plaintext() + s_ + "\n"
        return text


    def format_historique_plaintext(self, historique):
        """
        Formatte une historique de définition en texte simple.
        """
        text = "Historique:\n"
        for h_ in historique:
            text += self.list_item_plaintext() + h_["date"] + "\n"
            for c_ in h_["cit"]:
                text += self.list_item_plaintext(4, 1) + "{} ({}): {}\n".format(
                    c_["aut"],
                    c_["ref"],
                    c_["text"]
                )
        return text


    def format_etymologies(self, etymologie):
        """
        Formatte une liste d'étymologie en texte simple.
        """
        text = "Étymologie:\n"
        for e_ in etymologie:
            text += self.list_item_plaintext() + e_ + "\n"
        return text


    def format_plaintext(self,
                         no_quotes,
                         no_synonyms,
                         no_history,
                         no_etymology):
        """
        Formatte l'entrée en texte simple.
        Il est possible de désactiver la représentation de certaines parties
        de l'entrée grâce aux arguments nommés "no_*".
        Par convention, les noms de noeuds XML finissent par un '_'.
        """
        text = ""
        entete_ = self.entry.find("./entete")
        corps_ = self.entry.find("./corps")
        prononciation_ = entete_.find("./prononciation")
        nature_ = entete_.find("./nature")

        # Entête de la définition
        text += "Terme: {}\n".format(self.entry.attrib["terme"])
        if prononciation_ is not None:
            text += "Prononciation: {}\n".format(prononciation_.text)
        if nature_ is not None:
            text += "Nature: {}\n".format(nature_.text)

        # Variantes
        variantes = self.get_variantes(corps_, no_quotes)
        if variantes:
            text += self._subpart_separator
            text += self.format_variantes_plaintext(variantes)

        # Synonymes
        if not no_synonyms:
            synonymes = self.get_synonymes(self.entry)
            if synonymes:
                text += self._subpart_separator
                text += self.format_synonymes_plaintext(synonymes)

        # Historique
        if not no_history:
            historique = self.get_historique(self.entry)
            if historique:
                text += self._subpart_separator
                text += self.format_historique_plaintext(historique)

        # Étymologie
        if not no_etymology:
            etymologies = self.get_etymologie(self.entry)
            if etymologies:
                text += self._subpart_separator
                text += self.format_etymologies(etymologies)
        
        return text


    def format_html(self):
        pass


    def __repr__(self):
        return self.__str__()


    def __str__(self):
        return str(self.format())
