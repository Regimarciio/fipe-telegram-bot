import asyncio
import logging
import os
import requests
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
from telegram import Bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configurações
TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_HOST = os.getenv("DB_HOST", "db")
DB_NAME = os.getenv("DB_NAME", "fipe")
DB_USER = os.getenv("DB_USER", "fipe")
DB_PASS = os.getenv("DB_PASS", "fipe")

bot = Bot(token=TOKEN)

# Serviço FIPE
class FipeService:
    BASE_URL = "https://veiculos.fipe.org.br/api/veiculos"
    TIPO_VEICULO = 2
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://veiculos.fipe.org.br/"
        })
    
    def _post(self, endpoint: str, data: dict):
        try:
            url = f"{self.BASE_URL}/{endpoint}"
            resp = self.session.post(url, json=data, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Erro na API: {e}")
            return None
    
    def get_valor_por_codigo(self, codigo_fipe: str):
        """Busca valor atual pelo código FIPE"""
        data = {
            "codigoTipoVeiculo": self.TIPO_VEICULO,
            "codigoFipe": codigo_fipe
        }
        return self._post("ConsultarValorPorCodigoFipe", data)
    
    def parse_valor(self, response: dict) -> float:
        if not response:
            return 0
        valor_str = response.get("Valor", "R$ 0").replace("R$ ", "").replace(".", "").replace(",", ".")
        return float(valor_str)

fipe = FipeService()

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def get_veiculos_monitorados():
    """Busca todos os veículos com monitoramento ativo"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    
    cur.execute("""
        SELECT id, telegram_user_id, marca, modelo, ano, codigo_fipe, valor_atual
        FROM vehicles
        WHERE monitorando = TRUE
    """)
    
    veiculos = cur.fetchall()
    cur.close()
    conn.close()
    return veiculos

def atualizar_valor_veiculo(vehicle_id, novo_valor, valor_formatado):
    """Atualiza o valor do veículo e adiciona ao histórico"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Atualizar valor atual
    cur.execute("""
        UPDATE vehicles 
        SET valor_atual = %s, updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
    """, (novo_valor, vehicle_id))
    
    # Adicionar ao histórico
    cur.execute("""
        INSERT INTO price_history (vehicle_id, valor)
        VALUES (%s, %s)
    """, (vehicle_id, novo_valor))
    
    conn.commit()
    cur.close()
    conn.close()

async def verificar_e_notificar():
    """Verifica todos os veículos monitorados e notifica se houver mudança"""
    logger.info("🔍 Iniciando verificação de preços...")
    
    veiculos = get_veiculos_monitorados()
    logger.info(f"📊 Verificando {len(veiculos)} veículos monitorados")
    
    alertas_enviados = 0
    
    for veiculo in veiculos:
        try:
            # Buscar valor atual na FIPE
            resposta = fipe.get_valor_por_codigo(veiculo['codigo_fipe'])
            
            if resposta:
                novo_valor = fipe.parse_valor(resposta)
                valor_antigo = float(veiculo['valor_atual'])
                
                # Verificar se houve mudança (diferença maior que R$ 0,01)
                if abs(novo_valor - valor_antigo) > 0.01:
                    logger.info(f"💰 Mudança detectada: {veiculo['marca']} {veiculo['modelo']}")
                    logger.info(f"   Antigo: R$ {valor_antigo:.2f} -> Novo: R$ {novo_valor:.2f}")
                    
                    # Atualizar banco
                    atualizar_valor_veiculo(veiculo['id'], novo_valor, resposta.get("Valor", ""))
                    
                    # Formatar mensagem de alerta
                    variacao = novo_valor - valor_antigo
                    sinal = "📈" if variacao > 0 else "📉"
                    variacao_texto = f"{sinal} +R$ {abs(variacao):.2f}" if variacao > 0 else f"{sinal} -R$ {abs(variacao):.2f}"
                    
                    alerta = (
                        f"🚨 *ALERTA DE MUDANÇA NA FIPE* 🚨\n\n"
                        f"🏍 *{veiculo['marca']} {veiculo['modelo']}*\n"
                        f"📅 Ano: {veiculo['ano']}\n\n"
                        f"💰 *Valor anterior:* R$ {valor_antigo:.2f}\n"
                        f"💰 *Novo valor:* R$ {novo_valor:.2f}\n"
                        f"📊 *Variação:* {variacao_texto}\n\n"
                        f"📅 *Referência:* {resposta.get('MesReferencia', 'Atual')}\n\n"
                        f"🔔 Continue monitorando para mais atualizações!"
                    )
                    
                    # Enviar notificação
                    try:
                        await bot.send_message(
                            chat_id=veiculo['telegram_user_id'],
                            text=alerta,
                            parse_mode="Markdown"
                        )
                        alertas_enviados += 1
                        logger.info(f"✅ Alerta enviado para user {veiculo['telegram_user_id']}")
                    except Exception as e:
                        logger.error(f"❌ Erro ao enviar alerta: {e}")
                else:
                    logger.debug(f"Sem mudança: {veiculo['marca']} {veiculo['modelo']}")
            else:
                logger.warning(f"⚠️ Não foi possível consultar: {veiculo['marca']} {veiculo['modelo']}")
                
        except Exception as e:
            logger.error(f"❌ Erro ao processar veículo {veiculo['id']}: {e}")
    
    logger.info(f"✅ Verificação concluída! {alertas_enviados} alertas enviados.")
    return alertas_enviados

async def main():
    """Função principal para rodar o scheduler"""
    logger.info("🚀 Iniciando serviço de monitoramento FIPE...")
    
    while True:
        try:
            await verificar_e_notificar()
            
            # Aguardar 24 horas antes da próxima verificação
            logger.info("⏰ Próxima verificação em 24 horas...")
            await asyncio.sleep(24 * 60 * 60)  # 24 horas
            
        except Exception as e:
            logger.error(f"❌ Erro no ciclo de monitoramento: {e}")
            await asyncio.sleep(3600)  # Em caso de erro, tentar novamente em 1 hora

if __name__ == "__main__":
    asyncio.run(main())
