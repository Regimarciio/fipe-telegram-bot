import asyncio
import logging
import requests
from typing import Dict, List, Optional, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
import os
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv
import time

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_HOST = os.getenv("DB_HOST", "db")
DB_NAME = os.getenv("DB_NAME", "fipe")
DB_USER = os.getenv("DB_USER", "fipe")
DB_PASS = os.getenv("DB_PASS", "Fipe@2024Secure")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def init_db():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id SERIAL PRIMARY KEY,
                telegram_user_id BIGINT NOT NULL,
                marca VARCHAR(100) NOT NULL,
                modelo VARCHAR(200) NOT NULL,
                ano VARCHAR(20) NOT NULL,
                codigo_fipe VARCHAR(50) NOT NULL,
                valor_atual DECIMAL(10,2) NOT NULL,
                monitorando BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id SERIAL PRIMARY KEY,
                vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,
                valor DECIMAL(10,2) NOT NULL,
                data_coleta TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        cur.close()
        conn.close()
        logger.info("✅ Banco de dados inicializado")
    except Exception as e:
        logger.warning(f"Erro ao inicializar banco: {e}")

def salvar_veiculo(user_id, marca, modelo, ano, codigo_fipe, valor):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO vehicles (telegram_user_id, marca, modelo, ano, codigo_fipe, valor_atual)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (user_id, marca, modelo, ano, codigo_fipe, valor))
    vehicle_id = cur.fetchone()[0]
    cur.execute("""
        INSERT INTO price_history (vehicle_id, valor)
        VALUES (%s, %s)
    """, (vehicle_id, valor))
    conn.commit()
    cur.close()
    conn.close()
    return vehicle_id

def listar_veiculos(user_id, apenas_monitorando=True):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    query = "SELECT * FROM vehicles WHERE telegram_user_id = %s"
    if apenas_monitorando:
        query += " AND monitorando = TRUE"
    query += " ORDER BY created_at DESC"
    cur.execute(query, (user_id,))
    veiculos = cur.fetchall()
    cur.close()
    conn.close()
    return veiculos

class FipeService:
    BASE_URL = "https://parallelum.com.br/fipe/api/v1/motos"
    
    def _get(self, endpoint: str, retry=3):
        for tentativa in range(retry):
            try:
                url = f"{self.BASE_URL}/{endpoint}"
                logger.info(f"Chamando API: {url}")
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.warning(f"Tentativa {tentativa+1} falhou: {e}")
                if tentativa < retry - 1:
                    time.sleep(2)
        return None
    
    def get_marcas(self) -> List[Dict]:
        result = self._get("marcas")
        if result and isinstance(result, list):
            marcas = [{"Value": m["codigo"], "Label": m["nome"]} for m in result]
            return marcas
        return []
    
    def get_modelos(self, codigo_marca: int) -> List[Dict]:
        result = self._get(f"marcas/{codigo_marca}/modelos")
        if result and isinstance(result, dict):
            modelos = result.get("modelos", [])
            return [{"Value": m["codigo"], "Label": m["nome"]} for m in modelos]
        return []
    
    def get_anos(self, codigo_marca: int, codigo_modelo: int) -> List[Dict]:
        result = self._get(f"marcas/{codigo_marca}/modelos/{codigo_modelo}/anos")
        if result and isinstance(result, list):
            return [{"Value": a["codigo"], "Label": a["nome"]} for a in result]
        return []
    
    def get_valor(self, codigo_marca: int, codigo_modelo: int, ano_codigo: str) -> Optional[Dict]:
        return self._get(f"marcas/{codigo_marca}/modelos/{codigo_modelo}/anos/{ano_codigo}")
    
    def parse_valor(self, response: Dict) -> Dict:
        if not response:
            return {}
        try:
            valor_str = response.get("Valor", "R$ 0").replace("R$ ", "").replace(".", "").replace(",", ".")
            return {
                "valor": float(valor_str),
                "valor_formatado": response.get("Valor", "R$ 0"),
                "marca": response.get("Marca", ""),
                "modelo": response.get("Modelo", ""),
                "ano": response.get("AnoModelo", ""),
                "codigo_fipe": response.get("CodigoFipe", ""),
                "mes_referencia": response.get("MesReferencia", "Atual")
            }
        except:
            return {}

class Menus:
    ITENS_POR_PAGINA = 20
    
    @staticmethod
    def principal():
        keyboard = [
            [InlineKeyboardButton("🔎 Consultar moto", callback_data="consultar")],
            [InlineKeyboardButton("📊 Minhas motos", callback_data="minhas")],
            [InlineKeyboardButton("📈 Histórico", callback_data="historico")],
            [InlineKeyboardButton("❌ Remover", callback_data="remover")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def marcas(marcas: List[Dict]):
        keyboard = [[InlineKeyboardButton(m["Label"], callback_data=f"marca_{m['Value']}")] for m in marcas]
        keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="voltar")])
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def modelos_paginado(modelos: List[Dict], pagina: int, marca_cod: int, marca_nome: str):
        """Cria menu paginado de modelos"""
        total = len(modelos)
        inicio = pagina * Menus.ITENS_POR_PAGINA
        fim = min(inicio + Menus.ITENS_POR_PAGINA, total)
        
        keyboard = []
        for m in modelos[inicio:fim]:
            nome = m["Label"]
            if len(nome) > 35:
                nome = nome[:32] + "..."
            keyboard.append([InlineKeyboardButton(nome, callback_data=f"modelo_{m['Value']}")])
        
        # Botões de navegação
        nav_buttons = []
        if pagina > 0:
            nav_buttons.append(InlineKeyboardButton("◀️ Anterior", callback_data=f"page_modelo_{marca_cod}_{pagina-1}"))
        if fim < total:
            nav_buttons.append(InlineKeyboardButton("Próximo ▶️", callback_data=f"page_modelo_{marca_cod}_{pagina+1}"))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        # Info de página
        if total > Menus.ITENS_POR_PAGINA:
            keyboard.append([InlineKeyboardButton(f"📄 Página {pagina+1} de {(total-1)//Menus.ITENS_POR_PAGINA + 1}", callback_data="noop")])
        
        keyboard.append([InlineKeyboardButton("🔙 Voltar para marcas", callback_data="voltar_marcas")])
        
        return InlineKeyboardMarkup(keyboard), inicio, fim, total
    
    @staticmethod
    def anos(anos: List[Dict]):
        keyboard = [[InlineKeyboardButton(a["Label"], callback_data=f"ano_{a['Value']}")] for a in anos]
        keyboard.append([InlineKeyboardButton("🔙 Voltar", callback_data="voltar_modelos")])
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def monitor():
        keyboard = [
            [InlineKeyboardButton("✅ Monitorar", callback_data="monitorar_sim")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="voltar")]
        ]
        return InlineKeyboardMarkup(keyboard)

sessoes = {}
fipe = FipeService()
init_db()

async def start(update: Update, context):
    await update.message.reply_text(
        "🏍 *Monitor FIPE - Motos*\n\nEscolha uma opção:",
        reply_markup=Menus.principal(),
        parse_mode="Markdown"
    )

async def callback(update: Update, context):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    data = query.data

    if user_id not in sessoes:
        sessoes[user_id] = {}

    if data == "consultar":
        await query.edit_message_text("⏳ Carregando marcas...")
        marcas = fipe.get_marcas()
        if marcas:
            await query.edit_message_text(
                "🔍 *Selecione a marca:*",
                reply_markup=Menus.marcas(marcas),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("❌ Erro ao carregar marcas.")

    elif data.startswith("marca_"):
        codigo = int(data.split("_")[1])
        marcas = fipe.get_marcas()
        nome = next((m["Label"] for m in marcas if m["Value"] == codigo), "")
        sessoes[user_id]["marca_cod"] = codigo
        sessoes[user_id]["marca_nome"] = nome
        sessoes[user_id]["modelos"] = fipe.get_modelos(codigo)
        sessoes[user_id]["pagina_modelos"] = 0
        
        modelos = sessoes[user_id]["modelos"]
        if modelos:
            keyboard, inicio, fim, total = Menus.modelos_paginado(modelos, 0, codigo, nome)
            msg = f"📌 *{nome}*\n\n🔍 *Selecione o modelo:*\n*Mostrando {inicio+1}-{fim} de {total} modelos*"
            await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Nenhum modelo encontrado.")

    elif data.startswith("page_modelo_"):
        partes = data.split("_")
        marca_cod = int(partes[2])
        nova_pagina = int(partes[3])
        
        if "modelos" not in sessoes[user_id]:
            sessoes[user_id]["modelos"] = fipe.get_modelos(marca_cod)
        
        modelos = sessoes[user_id]["modelos"]
        sessoes[user_id]["pagina_modelos"] = nova_pagina
        
        keyboard, inicio, fim, total = Menus.modelos_paginado(modelos, nova_pagina, marca_cod, sessoes[user_id]["marca_nome"])
        msg = f"📌 *{sessoes[user_id]['marca_nome']}*\n\n🔍 *Selecione o modelo:*\n*Mostrando {inicio+1}-{fim} de {total} modelos*"
        await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")

    elif data.startswith("modelo_"):
        codigo = int(data.split("_")[1])
        modelos = sessoes[user_id]["modelos"]
        nome = next((m["Label"] for m in modelos if m["Value"] == codigo), "")
        sessoes[user_id]["modelo_cod"] = codigo
        sessoes[user_id]["modelo_nome"] = nome
        
        await query.edit_message_text(f"⏳ Carregando anos para {nome}...")
        anos = fipe.get_anos(sessoes[user_id]["marca_cod"], codigo)
        
        if anos:
            await query.edit_message_text(
                f"📌 *{sessoes[user_id]['marca_nome']} {nome}*\n\n📅 *Selecione o ano:*",
                reply_markup=Menus.anos(anos),
                parse_mode="Markdown"
            )
        else:
            await query.edit_message_text("❌ Nenhum ano encontrado.")

    elif data.startswith("ano_"):
        ano_codigo = data.split("_")[1]
        anos = fipe.get_anos(sessoes[user_id]["marca_cod"], sessoes[user_id]["modelo_cod"])
        ano_label = next((a["Label"] for a in anos if a["Value"] == ano_codigo), ano_codigo)
        
        await query.edit_message_text("⏳ Consultando valor FIPE...")
        valor_resp = fipe.get_valor(
            sessoes[user_id]["marca_cod"],
            sessoes[user_id]["modelo_cod"],
            ano_codigo
        )
        
        if valor_resp:
            valor = fipe.parse_valor(valor_resp)
            sessoes[user_id]["ultimo_valor"] = valor
            
            msg = (
                f"🏍 *{valor.get('marca', sessoes[user_id]['marca_nome'])} "
                f"{valor.get('modelo', sessoes[user_id]['modelo_nome'])}*\n\n"
                f"📅 *Ano:* {ano_label}\n\n"
                f"💰 *Valor FIPE:* {valor.get('valor_formatado', 'R$ 0')}\n\n"
                f"📅 *Referência:* {valor.get('mes_referencia', 'Atual')}\n\n"
                f"✅ Deseja monitorar este veículo?"
            )
            await query.edit_message_text(msg, reply_markup=Menus.monitor(), parse_mode="Markdown")
        else:
            await query.edit_message_text("❌ Erro ao consultar valor.")

    elif data == "monitorar_sim":
        if user_id in sessoes and "ultimo_valor" in sessoes[user_id]:
            valor = sessoes[user_id]["ultimo_valor"]
            try:
                salvar_veiculo(
                    user_id,
                    valor.get("marca", sessoes[user_id]["marca_nome"]),
                    valor.get("modelo", sessoes[user_id]["modelo_nome"]),
                    valor.get("ano", "2024"),
                    valor.get("codigo_fipe", ""),
                    valor.get("valor", 0)
                )
                await query.edit_message_text(
                    f"✅ *Veículo adicionado ao monitoramento!*\n\n"
                    f"🏍 {valor.get('marca')} {valor.get('modelo')}\n"
                    f"💰 Valor atual: {valor.get('valor_formatado')}\n\n"
                    f"🔔 Você receberá alertas quando o preço mudar!",
                    reply_markup=Menus.principal(),
                    parse_mode="Markdown"
                )
            except Exception as e:
                await query.edit_message_text(f"❌ Erro ao salvar: {e}")

    elif data == "minhas":
        veiculos = listar_veiculos(user_id)
        if veiculos:
            msg = "📊 *Suas motos monitoradas:*\n\n"
            for i, v in enumerate(veiculos, 1):
                msg += f"{i}. *{v['marca']} {v['modelo']}*\n"
                msg += f"   📅 {v['ano']} | 💰 R$ {float(v['valor_atual']):,.2f}\n\n"
            await query.edit_message_text(msg, reply_markup=Menus.principal(), parse_mode="Markdown")
        else:
            await query.edit_message_text("📭 *Nenhuma moto monitorada*", reply_markup=Menus.principal(), parse_mode="Markdown")

    elif data == "voltar":
        await query.edit_message_text(
            "🏍 *Monitor FIPE - Motos*\n\nEscolha uma opção:",
            reply_markup=Menus.principal(),
            parse_mode="Markdown"
        )

    elif data == "voltar_marcas":
        marcas = fipe.get_marcas()
        await query.edit_message_text("🔍 *Selecione a marca:*", reply_markup=Menus.marcas(marcas), parse_mode="Markdown")

    elif data == "voltar_modelos":
        modelos = sessoes[user_id]["modelos"]
        keyboard, inicio, fim, total = Menus.modelos_paginado(modelos, 0, sessoes[user_id]["marca_cod"], sessoes[user_id]["marca_nome"])
        msg = f"📌 *{sessoes[user_id]['marca_nome']}*\n\n🔍 *Selecione o modelo:*\n*Mostrando {inicio+1}-{fim} de {total} modelos*"
        await query.edit_message_text(msg, reply_markup=keyboard, parse_mode="Markdown")

    elif data == "noop":
        await query.answer()

    else:
        await query.edit_message_text("Opção em desenvolvimento.", reply_markup=Menus.principal())

async def main():
    if not TOKEN:
        logger.error("TOKEN não configurado!")
        return
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback))
    
    logger.info("✅ BOT FIPE INICIADO COM PAGINAÇÃO!")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
