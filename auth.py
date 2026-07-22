import hashlib
import pandas as pd
import streamlit as st
try:
    from streamlit_gsheets import GSheetsConnection
except ImportError:
    GSheetsConnection = None

class AuthManager:
    def __init__(self):
        self._initialize_db()

    def _hash_password(self, password):
        """Genera un hash SHA-256 de la contraseña."""
        return hashlib.sha256(password.encode()).hexdigest()

    def _initialize_db(self):
        """Crea la hoja con usuarios por defecto o actualiza credenciales."""
        # Definir credenciales base
        default_creds = {
            "admin": "admin123",
            "empleado": "olivia2024"
        }
        
        data = self._load_db()
            
        updated = False
        # Verificar/Crear usuarios por defecto
        for user, pwd in default_creds.items():
            pwd_hash = self._hash_password(pwd)
            if user not in data:
                data[user] = {
                    "password_hash": pwd_hash,
                    "score": 0,
                    "active_sessions": 0,
                    "role": "admin" if user == "admin" else "user",
                    "job_role": "Administrador" if user == "admin" else "Estudiante",
                    "language": "es" # Idioma por defecto
                }
                updated = True
            else:
                if "job_role" not in data[user]:
                    data[user]["job_role"] = "Administrador" if user == "admin" else "Estudiante"
                    updated = True
                if "language" not in data[user]:
                    data[user]["language"] = "es" # Añadir idioma a usuarios existentes
                    updated = True
                if data[user].get("password_hash") != pwd_hash:
                    # Actualizar contraseña si ha cambiado en código
                    # data[user]["password_hash"] = pwd_hash # Comentado para no sobreescribir contraseñas de usuarios existentes
                    updated = True
                
        if updated:
            self._save_db(data)

    def _load_db(self):
        """Carga la base de datos de usuarios desde Google Sheets."""
        if GSheetsConnection is None:
            return {}
        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            df = conn.read(worksheet="Users", ttl=0)
            
            # Lógica robusta para encontrar el spreadsheet
            url = None
            try:
                url = st.secrets["connections"]["gsheets"]["spreadsheet"]
            except (KeyError, AttributeError): # AttributeError para st.secrets local
                pass
            
            df = conn.read(spreadsheet=url, worksheet="Users", ttl=0) if url else conn.read(worksheet="Users", ttl=0)
            
            if df.empty:
                return {}
            df = df.dropna(how="all")
            if "username" not in df.columns:
                return {}
            return df.set_index("username").to_dict(orient="index")
        except Exception:
            return {}

    def _save_db(self, data):
        """Guarda la base de datos de usuarios en Google Sheets."""
        if GSheetsConnection is None:
            return
        try:
            df = pd.DataFrame.from_dict(data, orient="index")
            df.index.name = "username"
            df.reset_index(inplace=True)
            conn = st.connection("gsheets", type=GSheetsConnection)
            
            # Lógica robusta para encontrar el spreadsheet al guardar
            url = None
            try:
                url = st.secrets["connections"]["gsheets"]["spreadsheet"]
            except (KeyError, AttributeError):
                pass
            
            # Usar la URL si existe, de lo contrario, comportamiento por defecto
            conn.update(spreadsheet=url, worksheet="Users", data=df) if url else conn.update(worksheet="Users", data=df)
        except Exception as e:
            st.error(f"Error guardando en Google Sheets: {e}")

    def authenticate(self, username, password):
        """Verifica las credenciales del usuario."""
        data = self._load_db()
        user = data.get(username)
        
        if not user:
            return False
            
        # Verificar hash
        input_hash = self._hash_password(password)
        stored_hash = user.get("password_hash")
        
        # Compatibilidad: Si no hay hash (formato antiguo), actualizamos
        if not stored_hash and "password" in user:
            # Nota: Esto es solo para migración si fuera necesario
            return False 
            
        return input_hash == stored_hash

    def add_user(self, username, password, role="user", job_role="Estudiante"):
        """Añade un nuevo usuario a la base de datos."""
        data = self._load_db()
        if username in data:
            return False, "El usuario ya existe."
        
        data[username] = {
            "password_hash": self._hash_password(password),
            "score": 0,
            "active_sessions": 0,
            "role": role,
            "job_role": job_role,
            "language": "es"
        }
        self._save_db(data)
        return True, "Usuario creado correctamente."

    def change_password(self, username, new_password):
        """Cambia la contraseña de un usuario existente."""
        data = self._load_db()
        if username not in data:
            return False, "Usuario no encontrado."
            
        data[username]["password_hash"] = self._hash_password(new_password)
        self._save_db(data)
        return True, "Contraseña actualizada correctamente."

    def get_all_users(self):
        """Devuelve una lista con todos los nombres de usuario."""
        data = self._load_db()
        return list(data.keys())

    def get_user_profile(self, username):
        """Obtiene el perfil completo del usuario (progreso y rol)."""
        data = self._load_db()
        user = data.get(username, {})
        return {
            "score": user.get("score", 0),
            "active_sessions": user.get("active_sessions", 0),
            "job_role": user.get("job_role", "Estudiante"),
            "language": user.get("language", "es")
        }

    def update_user_job_role(self, username, job_role):
        """Actualiza el puesto/rol del usuario."""
        data = self._load_db()
        if username in data:
            data[username]["job_role"] = job_role
            self._save_db(data)
            return True
        return False

    def update_user_language(self, username, language):
        """Actualiza el idioma preferido del usuario."""
        data = self._load_db()
        if username in data:
            data[username]["language"] = language
            self._save_db(data)
            return True
        return False

    def update_user_progress(self, username, score=None, increment_session=False):
        """Actualiza la puntuación y sesiones del usuario."""
        data = self._load_db()
        
        if username not in data:
            # Si el usuario no existe, lo creamos
            data[username] = {"score": 0, "active_sessions": 0}
            
        if score is not None:
            data[username]["score"] = score
            
        if increment_session:
            data[username]["active_sessions"] = data[username].get("active_sessions", 0) + 1
            
        self._save_db(data)

# Instancia global para usar en la app
@st.cache_resource(ttl=3600)
def get_auth_manager():
    return AuthManager()