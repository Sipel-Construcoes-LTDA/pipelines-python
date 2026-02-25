import logging

# Configuração de Logging conforme PADROES_PROJETO.md
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- Configurações & Constantes ---
IDS_PLANILHAS = {
    "Bonfim": "1xRM5ArGu70p0sUtoLNpmOx-pEogwcJsPEO5kVT7jaZY",
    "Jacobina": "1oluRkWRsj6GuS8QJ0L3jFXi3FkLkCHCyVvbNpOjrdl4",
    "Juazeiro": "1lreFnHhjlEubtw_L6TDnQ1Ho3-_3VUDDmCOnN9Nsy2k",
}
GIDS = {
    "Bonfim": "1533241260",
    "Jacobina": "1995794361",
    "Juazeiro": "870879769",
}
