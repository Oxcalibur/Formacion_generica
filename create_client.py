import os
import subprocess
import sys
import json

# ================= CONFIGURACIÓN =================
JSON_FILE = "user_progress.json"
# =================================================

def run_command(command):
    """Ejecuta comandos de Git silenciosamente salvo error."""
    try:
        subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error al ejecutar: {command}")
        print(f"   Detalle: {e.stderr}")
        sys.exit(1)

def crear_cliente():
    print("\n✨ --- ASISTENTE DE CREACIÓN DE NUEVO CLIENTE (SOLO RAMA) --- ✨\n")

    # 1. DATOS DEL CLIENTE
    nombre_raw = input("1. Nombre del cliente (ej: Iberia, Demo Liderazgo): ")
    # Convertimos a formato URL (ej: demo-liderazgo)
    rama_cliente = nombre_raw.lower().replace(" ", "-")
    
    print(f"   🔹 Se creará la rama: '{rama_cliente}'")
    confirm = input("   ¿Continuar? (s/n): ")
    if confirm.lower() != 's': return

    # 2. GESTIÓN DE GIT
    print("\n⚙️  --- PROCESANDO GIT ---")
    print("   ⏳ Volviendo a main y actualizando...")
    run_command("git checkout main")
    run_command("git pull origin main")
    
    print(f"   ⏳ Creando rama '{rama_cliente}'...")
    # El -B fuerza la creación o reseteo si ya existía localmente
    run_command(f"git checkout -B {rama_cliente}")

    # 3. RESETEAR DATOS
    print("\n🧹 --- LIMPIEZA DE DATOS ---")
    # Resetear JSON de progreso para que el nuevo cliente empiece de 0
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        initial_data = {"admin": {"score": 0, "active_sessions": 0}}
        json.dump(initial_data, f, indent=4)
    print(f"   ✅ Archivo '{JSON_FILE}' reseteado.")

    # 4. SUBIDA A LA NUBE
    print("\n🚀 --- SUBIENDO A GITHUB ---")
    run_command("git add .")
    run_command(f'git commit -m "Alta cliente (Rama): {nombre_raw}"')
    
    print("   ⏳ Empujando a la nube...")
    run_command(f"git push --force --set-upstream origin {rama_cliente}")
    print("   ✅ Subida completada.")

    # 5. INSTRUCCIONES FINALES
    print(f"\n🎉 --- ¡ÉXITO! RAMA '{rama_cliente}' CREADA ---")
    print("Siguientes pasos:")
    print(f"1. Sube tus archivos (PDFs, Logo) directamente a GitHub en la rama '{rama_cliente}'.")
    print(f"2. Ve a tu plataforma de deploy y despliega esta rama.")

if __name__ == "__main__":
    crear_cliente()