import subprocess
import sys

# ================= CONFIGURACIÓN =================
# Escribe aquí los nombres EXACTOS de las ramas de tus clientes activos.
# Añade o quita líneas según necesites.
CLIENT_BRANCHES = [
    "demo-liderazgo",
     "demo-change",
    # "cliente-repsol",
]
# =================================================

def run_command(command, description):
    """Ejecuta comandos de terminal y maneja errores."""
    print(f"🔹 {description}...")
    try:
        # shell=True permite ejecutar el comando tal cual lo harías en la terminal
        # check=True detiene el script si el comando falla
        subprocess.run(command, shell=True, check=True, text=True)
        print("   ✅ Hecho")
    except subprocess.CalledProcessError:
        print(f"   ❌ ERROR CRÍTICO al ejecutar: {command}")
        print("   Deteniendo el script para seguridad.")
        sys.exit(1)

def update_clients():
    print("\n🤖 --- INICIANDO ACTUALIZADOR DE CLIENTES ---\n")

    # 1. Confirmación de seguridad
    print(f"Se actualizarán {len(CLIENT_BRANCHES)} clientes con el código actual de MAIN.")
    confirm = input("¿Estás seguro? (s/n): ")
    if confirm.lower() != 's':
        print("Operación cancelada.")
        return

    # 2. Preparar la base (MAIN)
    # Nos aseguramos de tener la última versión de tu código base antes de repartir
    print("\n--- 1. PREPARANDO MAIN ---")
    run_command("git checkout main", "Cambiando a rama Main")
    run_command("git pull origin main", "Descargando últimos cambios de GitHub")

    # 3. Bucle de actualización
    for branch in CLIENT_BRANCHES:
        print(f"\n--- 2. PROCESANDO: {branch.upper()} ---")
        
        try:
            # a) Cambiar a la rama del cliente
            run_command(f"git checkout {branch}", f"Saltando a rama {branch}")
            
            # b) Fusionar (Merge)
            # Esto trae el código de main a la rama del cliente.
            # El '-m' pone el mensaje automático para que no se abra un editor de texto.
            print(f"🔹 Fusionando código nuevo de Main...")
            subprocess.run(f"git merge main -m 'Auto-update: Actualización de código desde Main'", shell=True, check=True)
            print("   ✅ Fusión correcta")
            
            # c) Subir a la nube (Deploy)
            run_command(f"git push origin {branch}", f"Subiendo a GitHub (Deploy)")
            
        except subprocess.CalledProcessError:
            print(f"\n⚠️  CONFLICTO DETECTADO EN {branch}")
            print("   El script no pudo mezclar automáticamente (posible conflicto de archivos).")
            print("   El script se detendrá aquí. Por favor, resuelve el conflicto manualmente en VS Code.")
            sys.exit(1)

    # 4. Volver a casa
    print("\n--- 3. FINALIZANDO ---")
    run_command("git checkout main", "Regresando a Main")
    print("\n✨ ¡PROCESO COMPLETADO! Todos los clientes están actualizados.")

if __name__ == "__main__":
    update_clients()