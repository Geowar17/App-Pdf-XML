import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox

import pdfplumber
import xml.etree.ElementTree as ET
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm


# ---------- UTILIDADES -------------------------------------------------
def buscar(patron, texto, grupo=1, por_defecto="NO ENCONTRADO", flags=0):
    """
    Devuelve la coincidencia del regex o por_defecto.
    """
    m = re.search(patron, texto, flags)
    return m.group(grupo).strip() if m else por_defecto


def mm_to_pt(milimetros):
    """Convierte milímetros a puntos (1 mm ≈ 2.835 pt)."""
    return milimetros * mm


# ---------- EXTRACCIÓN PDF ➜ DICCIONARIO -------------------------------
def extraer_datos_sii(texto: str) -> dict:
    """
    Devuelve un diccionario con los campos extraídos de una factura SII.
    Si algún campo no se encuentra, se llena con 'NO ENCONTRADO'.
    """
    datos = {}

    # --- EMISOR --------------------------------------------------------
    datos["emisor_nombre"] = buscar(r"SERVICIOS TECNOLÓGICOS DE SEGURIDAD\n(.+)", texto)
    datos["emisor_giro"] = buscar(r"Giro:\s*(.+)", texto)
    datos["emisor_direccion"] = buscar(r"([A-Z].+RECOLETA)", texto)
    datos["emisor_email"] = buscar(r"eMail\s*:?\s*([^\s]+)", texto)
    # El primer RUT que aparece suele ser el del emisor
    datos["emisor_rut"] = buscar(r"R\.U\.T\.:\s*([\d\.]+\-\d)", texto)

    # --- RECEPTOR ------------------------------------------------------
    datos["receptor_nombre"] = buscar(r"SEÑOR\(ES\):\s*(.+)", texto)
    # El segundo RUT de la factura suele ser el receptor
    ruts = re.findall(r"R\.U\.T\.:\s*([\d\.]+\-\d)", texto)
    datos["receptor_rut"] = ruts[1] if len(ruts) > 1 else "NO ENCONTRADO"
    datos["receptor_giro"] = buscar(r"GIRO:\s*(ACTIVIDADES.+)", texto)
    datos["receptor_direccion"] = buscar(r"DIRECCION:\s*(.+)", texto)
    datos["receptor_comuna"] = buscar(r"COMUNA\s+(.+?)\s+CIUDAD", texto)
    datos["receptor_ciudad"] = buscar(r"CIUDAD:\s*(.+)", texto)

    # --- DOCUMENTO -----------------------------------------------------
    datos["numero"] = buscar(r"FACTURA ELECTRONICA\s*Nº(\d+)", texto)
    # Convertimos a ISO yyyy-mm-dd si es posible
    fecha_raw = buscar(r"Fecha Emision:\s*(.+)", texto)
    datos["fecha"] = fecha_raw  # lo dejamos literal; se puede normalizar
    descripcion = buscar(r"-\s*([A-Z].+?)\n", texto)
    datos["descripcion"] = descripcion
    datos["cantidad"] = buscar(r"\n(\d+)\s+" + re.escape(descripcion[:10]), texto)
    datos["precio_unitario"] = buscar(r"\n1\s+([\d\.]+)", texto).replace(".", "")
    datos["neto"] = buscar(r"MONTO NETO\s*\$\s*([\d\.]+)", texto).replace(".", "")
    datos["iva"] = buscar(r"I\.V\.A\.\s*19%?\s*\$\s*([\d\.]+)", texto).replace(".", "")
    datos["total"] = buscar(r"TOTAL\s*\$\s*([\d\.]+)", texto).replace(".", "")

    # Para sencillez dejamos un solo ítem
    datos["items"] = [
        {
            "descripcion": datos["descripcion"],
            "cantidad": datos["cantidad"] or "1",
            "precio_unitario": datos["precio_unitario"] or datos["neto"],
            "valor": datos["precio_unitario"] or datos["neto"],
        }
    ]
    return datos


# ---------- CONSTRUIR XML ---------------------------------------------
def construir_xml(datos: dict, ruta_salida: str):
    """
    Construye un XML según el diccionario y lo guarda.
    """
    factura = ET.Element("Factura")

    emisor = ET.SubElement(factura, "Emisor")
    for k in ["Nombre", "RUT", "Giro", "Direccion", "Email"]:
        ET.SubElement(emisor, k).text = datos.get(f"emisor_{k.lower()}", "NO ENCONTRADO")

    receptor = ET.SubElement(factura, "Receptor")
    for k in ["Nombre", "RUT", "Giro", "Direccion", "Comuna", "Ciudad"]:
        ET.SubElement(receptor, k).text = datos.get(f"receptor_{k.lower()}", "NO ENCONTRADO")

    documento = ET.SubElement(factura, "Documento")
    ET.SubElement(documento, "Numero").text = datos["numero"]
    ET.SubElement(documento, "Fecha").text = datos["fecha"]
    ET.SubElement(documento, "Tipo").text = "Factura Electrónica"

    items_node = ET.SubElement(documento, "Items")
    for itm in datos["items"]:
        item_node = ET.SubElement(items_node, "Item")
        for campo in ["descripcion", "cantidad", "precio_unitario", "valor"]:
            tag = campo.capitalize() if campo != "precio_unitario" else "PrecioUnitario"
            ET.SubElement(item_node, tag).text = itm[campo]

    totales = ET.SubElement(documento, "Totales")
    for k in ["neto", "iva", "total"]:
        ET.SubElement(totales, k.capitalize()).text = datos[k]

    tree = ET.ElementTree(factura)
    tree.write(ruta_salida, encoding="utf-8", xml_declaration=True)


# ---------- GENERAR PDF DESDE XML -------------------------------------
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet

import xml.etree.ElementTree as ET

def generar_pdf_desde_xml(ruta_xml: str, ruta_pdf: str):
    ns = {"sii": "http://www.sii.cl/SiiDte"}

    def find_text(root, path):
        el = root.find(path, ns)
        return el.text.strip() if el is not None and el.text else "—"

    tree = ET.parse(ruta_xml)
    root = tree.find(".//sii:Documento", ns)
    styles = getSampleStyleSheet()
    style_normal = styles["Normal"]
    style_normal.fontName = "Helvetica"
    style_normal.fontSize = 10
    style_normal.leading = 13

    doc = SimpleDocTemplate(
        ruta_pdf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    elements = []

    # Emisor
    emisor = [
        f"Emisor: {find_text(root, './/sii:Emisor/sii:RznSoc')}",
        f"RUT: {find_text(root, './/sii:Emisor/sii:RUTEmisor')}",
        f"Dirección: {find_text(root, './/sii:Emisor/sii:DirOrigen')}, {find_text(root, './/sii:Emisor/sii:CmnaOrigen')}",
    ]
    for line in emisor:
        elements.append(Paragraph(line, style_normal))
    elements.append(Spacer(1, 10))

    # Receptor
    receptor = [
        f"Receptor: {find_text(root, './/sii:Receptor/sii:RznSocRecep')}",
        f"RUT: {find_text(root, './/sii:Receptor/sii:RUTRecep')}",
        f"Dirección: {find_text(root, './/sii:Receptor/sii:DirRecep')}, {find_text(root, './/sii:Receptor/sii:CmnaRecep')}",
    ]
    for line in receptor:
        elements.append(Paragraph(line, style_normal))
    elements.append(Spacer(1, 10))

    # Documento
    folio = find_text(root, './/sii:IdDoc/sii:Folio')
    fecha = find_text(root, './/sii:IdDoc/sii:FchEmis')
    elements.append(Paragraph(f"<b>Factura Nº:</b> {folio} — <b>Fecha:</b> {fecha}", style_normal))
    elements.append(Spacer(1, 14))

    # Tabla de ítems
    data = [["Nº", "Descripción", "Cantidad", "Precio Unitario", "Precio Total"]]
    contador = 1
    for detalle in root.findall(".//sii:Detalle", ns):
        nombre = detalle.findtext("sii:NmbItem", default="—", namespaces=ns)
        cantidad = detalle.findtext("sii:QtyItem", default="1", namespaces=ns)
        precio = detalle.findtext("sii:PrcItem", default="0", namespaces=ns)
        monto = detalle.findtext("sii:MontoItem", default="0", namespaces=ns)
        data.append([str(contador), nombre[:90], cantidad, f"${precio}", f"${monto}"])
        contador += 1

    # Totales
    data.append(["", "", "", "Neto", f"${find_text(root, './/sii:Totales/sii:MntNeto')}"])
    data.append(["", "", "", "IVA", f"${find_text(root, './/sii:Totales/sii:IVA')}"])
    data.append(["", "", "", "Total", f"${find_text(root, './/sii:Totales/sii:MntTotal')}"])

    table = Table(data, colWidths=[15*mm, 85*mm, 20*mm, 30*mm, 30*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ]))

    elements.append(table)
    doc.build(elements)




# ---------- INTERFAZ DE USUARIO ---------------------------------------
def pdf_a_xml():
    ruta_pdf = filedialog.askopenfilename(
        title="Selecciona PDF de Factura SII",
        filetypes=[("PDF files", "*.pdf")],
    )
    if not ruta_pdf:
        return
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            texto = "\n".join([page.extract_text() or "" for page in pdf.pages])
        datos = extraer_datos_sii(texto)
        ruta_xml = filedialog.asksaveasfilename(
            title="Guardar XML",
            defaultextension=".xml",
            initialfile=f"factura_{datos['numero']}.xml",
            filetypes=[("XML files", "*.xml")],
        )
        if ruta_xml:
            construir_xml(datos, ruta_xml)
            messagebox.showinfo("Éxito", f"XML guardado en:\n{ruta_xml}")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo procesar el PDF:\n{e}")


def xml_a_pdf():
    ruta_xml = filedialog.askopenfilename(
        title="Selecciona XML de Factura",
        filetypes=[("XML files", "*.xml")],
    )
    if not ruta_xml:
        return
    ruta_pdf = filedialog.asksaveasfilename(
        title="Guardar PDF",
        defaultextension=".pdf",
        initialfile=f"{os.path.splitext(os.path.basename(ruta_xml))[0]}.pdf",
        filetypes=[("PDF files", "*.pdf")],
    )
    if ruta_pdf:
        try:
            generar_pdf_desde_xml(ruta_xml, ruta_pdf)
            messagebox.showinfo("Éxito", f"PDF guardado en:\n{ruta_pdf}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo generar el PDF:\n{e}")


def main():
    root = tk.Tk()
    root.title("Conversor PDF ↔ XML  (Factura SII)")

    frame = tk.Frame(root, padx=30, pady=30)
    frame.pack()

    tk.Button(
        frame,
        text="📄 PDF  ➜  XML",
        width=25,
        command=pdf_a_xml,
        padx=10,
        pady=10,
        bg="#d0f0d0",
    ).pack(pady=10)

    tk.Button(
        frame,
        text="📄 XML  ➜  PDF",
        width=25,
        command=xml_a_pdf,
        padx=10,
        pady=10,
        bg="#d0d0f0",
    ).pack(pady=10)

    root.mainloop()


if __name__ == "__main__":
    main()
