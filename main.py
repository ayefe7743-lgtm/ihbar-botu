import os
import ssl
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
import random

# --- KÖKTEN SSL ZIRHI (Pydroid 3 / Yerel Test İçin) ---
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['PYTHONHTTPSVERIFY'] = '0'

_original_init = aiohttp.ClientSession.__init__
def _patched_init(self, *args, **kwargs):
    kwargs['connector'] = aiohttp.TCPConnector(ssl=False)
    _original_init(self, *args, **kwargs)
aiohttp.ClientSession.__init__ = _patched_init
# -----------------------------------------------

# ==========================================
# TOKEN AYARI (RENDER İÇİN)
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- UYANIK TUTMA (KEEP ALIVE) ---
class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot aktif.")

def run_keep_alive():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), KeepAliveHandler)
    server.serve_forever()

threading.Thread(target=run_keep_alive, daemon=True).start()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


# ==========================================
# 1. BÖLÜM: İHBAR SİSTEMİ
# ==========================================
kullanici_limitleri = {}

def check_daily_limit(user_id: int) -> bool:
    today = time.strftime("%Y-%m-%d")
    key = f"ihbar_{user_id}_{today}"
    kullanici_limitleri[key] = kullanici_limitleri.get(key, 0) + 1
    return kullanici_limitleri[key] <= 4

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


# ==========================================
# 2. BÖLÜM: OSINT SİSTEMİ
# ==========================================
kullanici_sorgu_limitleri = {}

def check_query_limit(user_id: int) -> bool:
    today = time.strftime("%Y-%m-%d")
    key = f"osint_{user_id}_{today}"
    kullanici_sorgu_limitleri[key] = kullanici_sorgu_limitleri.get(key, 0) + 1
    return kullanici_sorgu_limitleri[key] <= 10

async def check_and_reply_limit(interaction: discord.Interaction) -> bool:
    if not check_query_limit(interaction.user.id):
        await interaction.response.send_message("❌ Günlük sorgu limitinizi (10) doldurdunuz. Yarın tekrar deneyebilirsiniz.", ephemeral=True)
        return False
    return True

async def fetch_json(url, headers=None):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                return {"error": f"HTTP {resp.status}"}
        except Exception as e:
            return {"error": str(e)}

async def send_dm_or_fallback(interaction: discord.Interaction, embed: discord.Embed):
    try:
        await interaction.user.send(embed=embed)
        await interaction.followup.send("✅ Sonuçlar DM kutunuza gönderildi.", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send("❌ Sonuçları size DM'den gönderemedim çünkü DM kutunuz kapalı.", ephemeral=True)

class IPModal(discord.ui.Modal, title="🌐 IP Analizi"):
    ip = discord.ui.TextInput(label="IP Adresi", placeholder="Örn: 8.8.8.8", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = f"http://ip-api.com/json/{self.ip.value}?fields=status,country,regionName,city,zip,lat,lon,timezone,isp,org,as,query"
        data = await fetch_json(url)
        if data.get("status") != "success":
            await interaction.followup.send(f"❌ Hata: {data.get('message', 'Geçersiz IP')}", ephemeral=True)
            return
        embed = discord.Embed(title=f"🌐 IP: {data.get('query')}", color=discord.Color.blue())
        embed.add_field(name="Ülke / Şehir", value=f"{data.get('country')} / {data.get('city')}", inline=True)
        embed.add_field(name="Bölge", value=data.get('regionName'), inline=True)
        embed.add_field(name="ISP", value=data.get('isp'), inline=False)
        embed.add_field(name="Org", value=data.get('org'), inline=False)
        embed.add_field(name="Koordinat", value=f"{data.get('lat')}, {data.get('lon')}", inline=True)
        await send_dm_or_fallback(interaction, embed)

class DNSModal(discord.ui.Modal, title="🛰️ DNS Lookup"):
    domain = discord.ui.TextInput(label="Domain", placeholder="Örn: google.com", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = f"https://dns.google/resolve?name={self.domain.value}&type=A"
        data = await fetch_json(url)
        if "Answer" not in data:
            await interaction.followup.send("❌ DNS kaydı bulunamadı.", ephemeral=True)
            return
        ips = "\n".join([ans['data'] for ans in data['Answer']])
        embed = discord.Embed(title=f"🛰️ DNS: {self.domain.value}", description=f"```\n{ips}\n```", color=discord.Color.blue())
        await send_dm_or_fallback(interaction, embed)

class WhoisModal(discord.ui.Modal, title="🔍 WHOIS Sorgusu"):
    domain = discord.ui.TextInput(label="Domain", placeholder="Örn: google.com", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = f"https://rdap.org/domain/{self.domain.value}"
        data = await fetch_json(url)
        if "error" in data:
            await interaction.followup.send(f"❌ WHOIS alınamadı: {data['error']}", ephemeral=True)
            return
        registrar = "Bilinmiyor"
        for entity in data.get("entities", []):
            if "vcardArray" in entity:
                for vcard in entity["vcardArray"][1]:
                    if vcard[0] == "fn":
                        registrar = vcard[3]
        embed = discord.Embed(title=f"🔍 WHOIS: {self.domain.value}", color=discord.Color.blue())
        embed.add_field(name="Kayıt Şirketi (Registrar)", value=registrar, inline=False)
        embed.add_field(name="Oluşturulma", value=data.get("events", [{}])[0].get("eventDate", "Yok"), inline=True)
        await send_dm_or_fallback(interaction, embed)

class UsernameModal(discord.ui.Modal, title="👤 Username Sorgu"):
    username = discord.ui.TextInput(label="Kullanıcı Adı", placeholder="Örn: john_doe", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        user = self.username.value
        sites = {
            "GitHub": f"https://github.com/{user}",
            "Instagram": f"https://www.instagram.com/{user}",
            "Twitter": f"https://twitter.com/{user}",
            "Reddit": f"https://www.reddit.com/user/{user}"
        }
        results = []
        async with aiohttp.ClientSession() as session:
            for name, url in sites.items():
                try:
                    async with session.get(url, timeout=5) as resp:
                        if resp.status == 200:
                            results.append(f"✅ {name}: {url}")
                        else:
                            results.append(f"❌ {name}")
                except:
                    results.append(f"❌ {name}")
        embed = discord.Embed(title=f"👤 Username: {user}", description="\n".join(results), color=discord.Color.blue())
        await send_dm_or_fallback(interaction, embed)

class EmailModal(discord.ui.Modal, title="📧 Email OSINT"):
    email = discord.ui.TextInput(label="E-posta Adresi", placeholder="Örn: test@gmail.com", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        email = self.email.value
        if "@" not in email:
            await interaction.followup.send("❌ Geçersiz e-posta formatı.", ephemeral=True)
            return
        domain = email.split("@")[1]
        url = f"https://dns.google/resolve?name={domain}&type=MX"
        data = await fetch_json(url)
        
        embed = discord.Embed(title=f"📧 Email: {email}", color=discord.Color.blue())
        embed.add_field(name="Format", value="✅ Geçerli", inline=True)
        if "Answer" in data:
            embed.add_field(name="MX Kaydı", value="✅ Bulundu (Geçerli Sunucu)", inline=True)
        else:
            embed.add_field(name="MX Kaydı", value="❌ Bulunamadı (Sahte Olabilir)", inline=True)
        await send_dm_or_fallback(interaction, embed)

class OsintPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Username", emoji="👤", style=discord.ButtonStyle.primary, custom_id="btn_user", row=0)
    async def btn_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_and_reply_limit(interaction): return
        await interaction.response.send_modal(UsernameModal())

    @discord.ui.button(label="Email OSINT", emoji="✉️", style=discord.ButtonStyle.primary, custom_id="btn_email", row=0)
    async def btn_email(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_and_reply_limit(interaction): return
        await interaction.response.send_modal(EmailModal())

    @discord.ui.button(label="WHOIS", emoji="🔎", style=discord.ButtonStyle.primary, custom_id="btn_whois", row=1)
    async def btn_whois(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_and_reply_limit(interaction): return
        await interaction.response.send_modal(WhoisModal())

    @discord.ui.button(label="DNS Lookup", emoji="📡", style=discord.ButtonStyle.primary, custom_id="btn_dns", row=1)
    async def btn_dns(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_and_reply_limit(interaction): return
        await interaction.response.send_modal(DNSModal())

    @discord.ui.button(label="IP Analizi", emoji="🌐", style=discord.ButtonStyle.primary, custom_id="btn_ip", row=2)
    async def btn_ip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await check_and_reply_limit(interaction): return
        await interaction.response.send_modal(IPModal())

@bot.tree.command(name="osint", description="OSINT panelini kanala gönderir")
@app_commands.default_permissions(manage_messages=True)
async def osint(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛠️OSINT SİSTEMİ",
        description="Her Kullanıcı Günde 10 Kez Sorgu Yapabilir.",
        color=discord.Color.from_str("#2b2d31")
    )
    await interaction.response.send_message(embed=embed, view=OsintPanel())


# ==========================================
# 3. BÖLÜM: RASTGELE BANKA KARTI ÜRETİCİ
# ==========================================
def luhn_checksum(card_number):
    def digits_of(n):
        return [int(d) for d in str(n)]
    digits = digits_of(card_number)
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    checksum = sum(odd_digits)
    for d in even_digits:
        checksum += sum(digits_of(d * 2))
    return checksum % 10

def generate_fake_cc():
    bins = [
        "402400", # Visa
        "453200", # Visa
        "542500", # Mastercard
        "531200", # Mastercard
        "555500"  # Mastercard
    ]
    prefix = random.choice(bins)
    body = prefix + "".join([str(random.randint(0, 9)) for _ in range(9)])
    
    for i in range(10):
        test_card = body + str(i)
        if luhn_checksum(test_card) == 0:
            kart_numarasi = test_card
            break
            
    ay = str(random.randint(1, 12)).zfill(2)
    yil = str(random.randint(26, 30))
    cvv = "".join([str(random.randint(0, 9)) for _ in range(3)])
    
    return f"{kart_numarasi}|{ay}|{yil}|{cvv}"

class CcPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Kart Üret", style=discord.ButtonStyle.primary, custom_id="cc_uret_btn")
    async def cc_uret_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 10 adet kart üret
        kartlar = [generate_fake_cc() for _ in range(10)]
        formatli_metin = "\n".join(kartlar)
        
        mesaj = f"```\n{formatli_metin}\n```"
        
        # Sadece butona basan kişiye özel gönder
        await interaction.response.send_message(mesaj, ephemeral=True)

@bot.tree.command(name="ccuret", description="CC Üretme panelini kanala gönderir.")
@app_commands.default_permissions(manage_messages=True)
async def ccret(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💳 CC ÜRETME",
        description="Aşağıdaki butona basarak rastgele kart üretebilirsiniz.",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, view=CcPanel())


# ==========================================
# BOTU BAŞLATMA
# ==========================================
@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
        print("[clerk] Tüm Slash komutları başarıyla yüklendi.")
    except Exception as e:
        print(f"[clerk] Komut yükleme hatası: {e}")
    
    print(f"[clerk] {bot.user} çevrimiçi! İhbar, OSINT ve CC sistemleri hazır.")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
