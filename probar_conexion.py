from dotenv import load_dotenv
import os
from supabase import create_client

load_dotenv()

cliente = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY"),
)

# Intenta leer la tabla (debe existir ya, después del SQL)
respuesta = cliente.table("conocimiento_jim").select("id").limit(1).execute()
print("✓ Conexión exitosa a Supabase")