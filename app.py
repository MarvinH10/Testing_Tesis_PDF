import os
import fitz  # PyMuPDF para el manejo de PDF
import re
import spacy
import pytesseract  # Para el uso de OCR en caso de que el PDF sea escaneado
from PIL import Image
from flask import Flask, render_template, request

# Carga el modelo de spaCy para español
nlp = spacy.load("es_core_news_sm")

# Configuración del tesseract para OCR
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf"}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Estructura y subsecciones esperadas en las tesis
ESTRUCTURA_ESPERADA = [
    "resumen",
    "índice",
    "introducción",
    "marco teórico",
    "metodología",
    "resultados",
    "conclusiones",
    "referencias bibliográficas",
    "anexos",
]

SUB_SECCIONES_ESPERADAS = {
    "marco teórico": [
        "revisión de la literatura",
        "teorías relacionadas",
        "tabla de operacionalización de variables",
    ],
    "metodología": [
        "diseño de investigación",
        "objetivos generales",
        "objetivos específicos",
    ],
}


# Función para verificar si el archivo es un PDF
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# Función para extraer texto de un archivo PDF usando PyMuPDF
def extract_text_from_pdf(filepath):
    doc = fitz.open(filepath)
    text = ""
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text += page.get_text("text")  # Extrae el texto como cadena
    return text


# En caso de que el PDF sea escaneado y se necesite OCR
def extract_text_with_ocr(filepath):
    doc = fitz.open(filepath)
    text = ""
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pix = page.get_pixmap()  # Convierte la página en imagen para OCR
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        text += pytesseract.image_to_string(img)  # Usa OCR para extraer texto
    return text


# Divide el texto en secciones utilizando patrones de títulos comunes
def dividir_secciones(texto):
    patrones = [
        r"\bResumen\b",
        r"\bÍndice\b",
        r"\bIntroducción\b",
        r"\bMarco[^\n]*Te[oó]rico\b",
        r"\bMetodolog[ií]a\b",
        r"\bResultados\b",
        r"\bConclusiones\b",
        r"\bReferencias\b",
        r"\bAnexos\b",
        r"\bOperacionalizaci[oó]n de Variables\b",
    ]

    secciones = {}
    current_section = None
    current_content = []
    tabla_patron = r"(variable.*dimensiones.*indicadores.*unidad de medida)"  # Para detectar tablas de operacionalización

    for line in texto.split("\n"):
        line = line.strip().lower()
        matched = False

        # Identificar los títulos de secciones con expresiones regulares
        for patron in patrones:
            if re.search(patron.lower(), line):
                if current_section:
                    secciones[current_section] = "\n".join(current_content).strip()
                current_section = re.sub(r"[^a-zA-Záéíóúüñ]", " ", line)
                current_content = []
                matched = True
                break

        if re.search(tabla_patron, line):  # Detectar tablas de operacionalización
            current_section = "operacionalización de variables"
            current_content.append(line)
            matched = True

        if not matched and current_section:
            current_content.append(line)

    if current_section:
        secciones[current_section] = "\n".join(current_content).strip()

    return secciones


# Funciones para revisar la estructura y subsecciones de la tesis
def revisar_estructura(secciones):
    observaciones = []
    for seccion in ESTRUCTURA_ESPERADA:
        if seccion not in secciones:
            observaciones.append(f"Falta la sección: {seccion.capitalize()}.")
    return observaciones


def revisar_subsecciones(secciones):
    observaciones = []
    for seccion, subsecciones in SUB_SECCIONES_ESPERADAS.items():
        contenido = secciones.get(seccion, "")
        for sub in subsecciones:
            if (
                sub == "tabla de operacionalización de variables"
                and "operacionalización de variables" in secciones
            ):
                continue
            if sub not in contenido:
                observaciones.append(
                    f"Falta la subsección: '{sub}' en la sección {seccion.capitalize()}."
                )
    return observaciones


def revisar_contenido(secciones):
    observaciones = []
    introduccion = secciones.get("introducción", "")
    if len(introduccion.split()) < 100:
        observaciones.append("La sección de Introducción parece demasiado corta.")
    return observaciones


def revisar_metodologia(secciones):
    observaciones = []
    metodologia = secciones.get("metodología", "")
    if "diseño de investigación" not in metodologia:
        observaciones.append("Falta la descripción del diseño de investigación.")
    if (
        "objetivos generales" not in metodologia
        and "objetivos específicos" not in metodologia
    ):
        observaciones.append("Faltan los objetivos generales o específicos.")
    return observaciones


def analizar_texto(texto):
    observaciones = []
    secciones = dividir_secciones(texto)

    observaciones.extend(revisar_estructura(secciones))
    observaciones.extend(revisar_subsecciones(secciones))
    observaciones.extend(revisar_contenido(secciones))

    return observaciones


@app.route("/")
def upload_file():
    return render_template("upload.html")


@app.route("/uploader", methods=["POST"])
def uploader():
    if "file" not in request.files:
        return "No file part", 400
    file = request.files["file"]
    if file.filename == "":
        return "No selected file", 400
    if file and allowed_file(file.filename):
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
        file.save(filepath)

        # Leer el texto del PDF
        texto = extract_text_from_pdf(filepath)

        secciones = dividir_secciones(texto)

        # Revisar las secciones y contenido del documento
        observaciones_contenido = revisar_contenido(secciones)
        observaciones_metodologia = revisar_metodologia(secciones)
        observaciones_estructura = analizar_texto(texto)

        return render_template(
            "result.html",
            observaciones_contenido=observaciones_contenido,
            observaciones_metodologia=observaciones_metodologia,
            observaciones_estructura=observaciones_estructura,
        )
    return "Invalid file type", 400


if __name__ == "__main__":
    app.run(debug=True)
