# Usa una imagen base que sea ligera y tenga las herramientas necesarias
# Esto instala Python 3.9 (igual que en tu Mac) y Wine.
FROM debian:bookworm-slim

# Evita preguntas interactivas durante la instalación
ENV DEBIAN_FRONTEND=noninteractive

# Instala dependencias básicas y Wine
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \ 
    wine64 \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Crea un directorio de trabajo dentro del contenedor
WORKDIR /app

# --- AHORA CREAMOS Y ACTIVAMOS UN ENTORNO VIRTUAL DENTRO DEL CONTENEDOR ---
ENV VIRTUAL_ENV=/app/venv 
# Define la ubicación de tu entorno virtual
ENV PATH="$VIRTUAL_ENV/bin:$PATH" 
# Agrega el binario del venv al PATH para que pip funcione

RUN python3 -m venv "$VIRTUAL_ENV" # Crea el entorno virtual

# Copia tu archivo de requisitos e instala las dependencias de Python
# Asegúrate de que pyinstaller también esté en requirements.txt
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt # Ahora pip instalará en el venv

# Copia tu script Python al contenedor
COPY inicio.py .

# Comando para ejecutar PyInstaller.
# Nota: Como el venv está activo, 'pyinstaller' se ejecutará desde el venv
CMD ["wine", "pyinstaller", "--onefile", "--distpath", ".", "--workpath", "/tmp/build", "inicio.py"]