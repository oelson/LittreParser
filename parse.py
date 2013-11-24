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
        Récupère un noeud Element correspondant au mot recherché.
        Retourne une instance de la classe "entry".
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
    
    # Liste à puce
    _nbsp = u"\u00A0"
    _bullet = u"\u2219"
    _w_bullet = u"\u25E6"
    _q = u"\u201C\u201D"

    # Format de l'entête
    entete_format = (
        "terme: {}\n"
        "prononciation: {}\n"
        "nature: {}"
    )
    
    # Format d'une variante
    variante_format = _nbsp*2 + "{}."+_nbsp+"{}"
    
    # Format d'une citation
    citation_format = _nbsp*4+_bullet+_nbsp+"{} ({}):"+_nbsp+_q[0]+"{}"+_q[1]
    
    # Format d'un item de liste quelconque
    li_format = _nbsp*2 + _bullet + _nbsp + "{}"


    def __init__(self, mot, entry):
        self.mot = mot
        self.entry = entry


    def __dict__(self):
        """
        Retourne la description de l'objet sous la forme d'un dictionnaire.
        """
        return _xml2dict(self.entry)


    def get_variante_text(self, v):
        """
        Retourne le texte définissant une variante.
        Ce texte s'étale éventuellement sur des noeuds collés à des morceaux
        de texte.
        """
        text = v.text.rstrip() if v.text else ""
        # workaround: "find()" ne fonctionne pas, certainement à cause de
        # l'imbrication de noeuds texte et non-texte au sein d'un même
        # élément
        for sem in v.iter("semantique"):
            if sem.text:
                text += sem.text.rstrip()
            if sem.tail:
                text += sem.tail.rstrip()
        return text

    def get_variantes_as_plaintext(self, corps_):
        """
        """
        variantes = []
        for v in corps_.iterfind("./variante"):
            variante = self.variante_format.format(
                v.attrib.get("num") or "?",
                self.get_variante_text(v)
            )
            # adjoint les éventuelles citations propres à une variante
            citations = self.get_citations_as_plaintext(v)
            if citations:
                variante += "\n" + citations
            variantes.append(variante)
        if variantes:
            return "variantes:\n" + "\n".join(variantes)
        return ""


    def get_citations_as_plaintext(self, variante_):
        """
        """
        citations = []
        for c in variante_.iterfind("./cit"):
            citation = self.citation_format.format(
                c.attrib["aut"] or "aut. inc.",
                c.attrib["ref"] or "ref. inc.",
                c.text
            )
            citations.append(citation)
        return "\n".join(citations)


    def get_synonymes_as_plaintext(self, entry_):
        """
        """
        synonymes = []
        for synonymes_ in entry_.iterfind("./rubrique[@nom='SYNONYME']"):
            for syn in synonymes_.iter("indent"):
                synonymes.append(self.li_format.format(syn.text.rstrip()))
        if synonymes:
            return "synonymes:\n" + "\n".join(synonymes)
        return ""

    
    def get_historique_as_plaintext(self, entry_):
        """
        """
        historique = []
        rubrique_ = entry_.find("./rubrique[@nom='HISTORIQUE']")
        for indent in rubrique_.iter("indent"):
            # siècle
            h = indent.text.rstrip()
            citations = []
            for c in indent.iter("cit"):
                citation = self.citation_format.format(
                    c.attrib["aut"] or "aut. inc.",
                    c.attrib["ref"] or "ref. inc.",
                    c.text
                )
                citations.append(citation)
            if citations:
                h += "\n" + "\n".join(citations)
            historique.append(h)
        if historique:
            return "historique:\n" + "\n".join(historique)
        return ""


    def format(self, format_type=FORMAT_TYPE_PLAINTEXT):
        """
        """
        if format_type == self.FORMAT_TYPE_PLAINTEXT:
            return self.format_plaintext()
        elif format_type == self.FORMAT_TYPE_HTML:
            return self.format_html()
        else:
            raise ValueError

    
    def format_plaintext(self):
        """
        Les noms de noeuds XML finissent par un '_'.
        """
        text = ""
        entete_ = self.entry.find("./entete")
        corps_ = self.entry.find("./corps")
        prononciation_ = entete_.find("./prononciation")
        nature_ = entete_.find("./nature")
        # Entête de la définition
        text += self.entete_format.format(
            self.entry.attrib["terme"],
            prononciation_.text,
            nature_.text,
        )
        # Variantes
        text += "\n" + self.get_variantes_as_plaintext(corps_)
        # Synonymes
        text += "\n" + self.get_synonymes_as_plaintext(self.entry)
        # Historique
        text += "\n" + self.get_historique_as_plaintext(self.entry)
        
        return text


    def format_html(self):
        pass


    def __repr__(self):
        return self.__str__()


    def __str__(self):
        return str(self.format())
