[Mensaje usuario]
       ↓
[Aris crea paquete contextual]
       ↓
[GPT clasifica y razona]
       ↓
¿GPT devuelve READY?
       ├─ Sí → Aris ejecuta action y guarda
       │
       └─ No
          ↓
   ¿GPT devuelve NEEDS_CLARIFICATION?
       ├─ Sí → Aris guarda pending_action y pregunta
       │       ↓
       │   [Usuario responde]
       │       ↓
       │   Aris envía respuesta + pending + candidatos a GPT
       │
       └─ No
          ↓
   ¿GPT devuelve GENERAL_QUERY?
       ├─ Sí → Aris muestra respuesta
       └─ No → Aris pide reformulación