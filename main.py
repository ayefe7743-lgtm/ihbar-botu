import os
import discord
from discord import app_commands
from discord.ext import commands
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Token'ı Railway/Render'in çevre değişkenlerinden okuyacak
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- UYANIK TUTMA (KEEP ALIVE) ---
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot aktif.")

def run_keep_alive():
    # Render'ın atadığı portu kullan, yoksa 8080
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
    server.serve_forever()

threading.Thread(target=run_keep_alive, daemon=True).start()
# ---------------------------------

kullanici_limitleri = {}

def check_daily_limit(user_id: int) -> bool:
    today = time.strftime("%Y-%m-%d")
    key = f"{user_id}_{today}"
    kullanici_limitleri[key] = kullanici_limitleri.get(key, 0) + 1
    return kullanici_limitleri[key] <= 4

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

class IhbarModal(discord.ui.Modal, title="🚨 İhbar Formu"):
    il = discord.ui.TextInput(label="İl", required=True, placeholder="Örn: İstanbul")
    ilce = discord.ui.TextInput(label="İlçe", required=True, placeholder="Örn: Kadıköy")
    mahalle = discord.ui.TextInput(label="Mahalle", required=True, placeholder="Örn: Caferağa")
    adres = discord.ui.TextInput(label="Cadde / Sokak & Kapı No", required=True, placeholder="Örn: Moda Caddesi No:5 D:3")
    olay = discord.ui.TextInput(label="Olay", style=discord.TextStyle.paragraph, required=True, placeholder="Olayı kısaca anlatın...")

    async def on_submit(self, interaction: discord.Interaction):
        if not check_daily_limit(interaction.user.id):
            await interaction.response.send_message("❌ Günlük ihbar limitinizi (4) doldurdunuz.", ephemeral=True)
            return
        await interaction.response.send_message("✅ İhbarınız başarıyla alındı. Sistem 112'yi arayarak durumu bildirecek.", ephemeral=True)

class IhbarPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🚨 İhbar Oluştur", style=discord.ButtonStyle.danger, custom_id="ihbar_olustur_btn")
    async def ihbar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(IhbarModal())

@bot.tree.command(name="ihbarr", description="İhbar panelini kanala gönderir")
@app_commands.default_permissions(manage_messages=True)
async def ihbarr(interaction: discord.Interaction):
    embed = discord.Embed(title="🚨 İhbar Sistemi", color=discord.Color.red())
    embed.add_field(name="📄 Gerekli Bilgiler", value="**İl** *(Gerekli)*\n**İlçe** *(Gerekli)*\n**Mah.** *(Gerekli)*\n**Cadde / Sokak & Kapı No**\n*(Cadde /Sokak zorunlu , Kapı no isteğe bağlı)*", inline=False)
    embed.add_field(name="⏳ Günlük Limit", value="Her kullanıcı günde **4** kez ihbar yapabilir.", inline=False)
    embed.set_footer(text="Aşağıdaki butonu kullanarak ihbar oluşturabilirsiniz.")
    await interaction.response.send_message(embed=embed, view=IhbarPanel())

@bot.tree.command(name="form", description="Buton çalışmazsa, formu doğrudan buradan açın")
async def form(interaction: discord.Interaction):
    await interaction.response.send_modal(IhbarModal())

@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
    except Exception as e:
        print(f"[clerk] Komut yükleme hatası: {e}")
    print(f"[clerk] {bot.user} çevrimiçi! Sistem hazır.")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
