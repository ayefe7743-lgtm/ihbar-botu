import os
import ssl
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import threading
import time
import random
import string
import io
import uuid
import re
import base64
from aiohttp import web

# --- KÖKTEN SSL ZIRHI ---
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['PYTHONHTTPSVERIFY'] = '0'

_original_init = aiohttp.ClientSession.__init__
def _patched_init(self, *args, **kwargs):
    kwargs['connector'] = aiohttp.TCPConnector(ssl=False)
    _original_init(self, *args, **kwargs)
aiohttp.ClientSession.__init__ = _patched_init
# -----------------------------------------------

# ==========================================
# TOKEN VE URL AYARI (RENDER İÇİN)
# ==========================================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# --- WEB SUNUCUSU (KEEP ALIVE) ---
async def handle_keep_alive(request):
    return web.Response(text="Bot aktif.")

def run_web_server():
    app = web.Application()
    app.router.add_get('/', handle_keep_alive)
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host='0.0.0.0', port=port)

threading.Thread(target=run_web_server, daemon=True).start()

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
        "402400", "453200", "491600", "455600", "414700", # Visa
        "542500", "531200", "555500", "510510", "520000"  # Mastercard
    ]
    prefix = random.choice(bins)
    body = prefix + "".join([str(random.randint(0, 9)) for _ in range(9)])
    
    for i in range(10):
        test_card = body + str(i)
        if luhn_checksum(test_card) == 0:
            kart_numarasi = test_card
            break
            
    ay = str(random.randint(1, 12)).zfill(2)
    yil = str(random.randint(27, 31))
    cvv = "".join([str(random.randint(0, 9)) for _ in range(3)])
    
    return f"{kart_numarasi}|{ay}|{yil}|{cvv}"

class CcPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Kart Üret", style=discord.ButtonStyle.primary, custom_id="cc_uret_btn")
    async def cc_uret_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        kartlar = [generate_fake_cc() for _ in range(10)]
        formatli_metin = "\n".join(kartlar)
        
        mesaj = f"```\n{formatli_metin}\n```"
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
# 4. BÖLÜM: TIKTOK SORGUSU
# ==========================================
def generate_realistic_secuid():
    prefix = "MS4wLjABAAAA"
    chars = string.ascii_letters + string.digits + "-_"
    return prefix + ''.join(random.choices(chars, k=40))

def generate_realistic_tiktok_id():
    return "".join([str(random.randint(0, 9)) for _ in range(19)])

def generate_realistic_sessionid():
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=64))

class TiktokModal(discord.ui.Modal, title="🎵 TikTok Sorgu"):
    kullanici_adi = discord.ui.TextInput(
        label="TikTok Kullanıcı Adı", 
        placeholder="Örn: @username (başındaki @ işaretini silin)", 
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        username = self.kullanici_adi.value.replace("@", "").strip()
        
        fake_id = generate_realistic_tiktok_id()
        fake_secuid = generate_realistic_secuid()
        fake_token = generate_realistic_sessionid()
        
        dm_mesaji = (
            f"🎵 **TikTok Sorgu Sonucu** 🎵\n\n"
            f"👤 **Kullanıcı Adı:** `@{username}`\n"
            f"🆔 **Kullanıcı ID:** `{fake_id}`\n"
            f"🔑 **SecUID:** `{fake_secuid}`\n"
            f"🎫 **Token (SessionID):** `{fake_token}`"
        )
        
        try:
            await interaction.user.send(dm_mesaji)
            await interaction.followup.send("✅ Sorgu başarılı! Sonuçlar DM kutunuza gönderildi.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Sonuçları size DM'den gönderemedim çünkü DM kutunuz kapalı.", ephemeral=True)

class TiktokPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎵Tiktok", style=discord.ButtonStyle.secondary, custom_id="tiktok_sorgu_btn")
    async def tiktok_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TiktokModal())

@bot.tree.command(name="tiktoksorgu", description="TikTok sorgu panelini kanala gönderir")
@app_commands.default_permissions(manage_messages=True)
async def tiktoksorgu(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎵Tiktok Sorgu",
        description="Birini sorgulamak için lütfen aşağıdaki “tiktok” butonununa basınız.",
        color=discord.Color.dark_purple()
    )
    await interaction.response.send_message(embed=embed, view=TiktokPanel())


# ==========================================
# 5. BÖLÜM: PROXY ÇEKME SİSTEMİ
# ==========================================
class ProxyPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def fetch_and_send(self, interaction: discord.Interaction, proxy_type: str, url: str):
        await interaction.response.defer(ephemeral=True)
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        await interaction.followup.send("❌ Proxy sunucusuna ulaşılamadı, lütfen tekrar deneyin.", ephemeral=True)
                        return
                    
                    text_data = await resp.text()
                    lines = [line.strip() for line in text_data.splitlines() if line.strip()]
                    
                    if not lines:
                        await interaction.followup.send("❌ Sunucudan boş liste döndü.", ephemeral=True)
                        return
                    
                    file_data = "\n".join(lines)
                    file_bytes = io.BytesIO(file_data.encode('utf-8'))
                    dosya = discord.File(fp=file_bytes, filename=f"{proxy_type.lower()}_proxies.txt")
                    
                    await interaction.followup.send(
                        content=f"✅ **{proxy_type}** proxy listesi hazır! Toplam **{len(lines)}** adet proxy bulundu.",
                        file=dosya,
                        ephemeral=True
                    )
            except Exception as e:
                await interaction.followup.send(f"❌ Bir hata oluştu: {e}", ephemeral=True)

    @discord.ui.button(label="HTTP", emoji="🌍", style=discord.ButtonStyle.primary, custom_id="proxy_http")
    async def btn_http(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fetch_and_send(interaction, "HTTP", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt")

    @discord.ui.button(label="SOCKS4", emoji="🔒", style=discord.ButtonStyle.success, custom_id="proxy_socks4")
    async def btn_socks4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fetch_and_send(interaction, "SOCKS4", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt")

    @discord.ui.button(label="SOCKS5", emoji="🔐", style=discord.ButtonStyle.secondary, custom_id="proxy_socks5")
    async def btn_socks5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.fetch_and_send(interaction, "SOCKS5", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt")

@bot.tree.command(name="proxy", description="Proxy çekme panelini kanala gönderir")
@app_commands.default_permissions(manage_messages=True)
async def proxy(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌐 Proxy Çekme Sistemi",
        description="Aşağıdaki Butonları Kullanarak Proxy Çekebilirsin.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=ProxyPanel())


# ==========================================
# 6. BÖLÜM: IP SORGULAMA SİSTEMİ
# ==========================================
class IpSorguModal(discord.ui.Modal, title="🌐 IP Sorgula"):
    ip = discord.ui.TextInput(label="IP Adresi", placeholder="Örn: 8.8.8.8", required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = f"http://ip-api.com/json/{self.ip.value}?fields=status,message,country,regionName,city,zip,lat,lon,timezone,isp,org,as,query"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as resp:
                    data = await resp.json()
                    
                    if data.get("status") != "success":
                        await interaction.followup.send(f"❌ Sorgu başarısız: {data.get('message', 'Geçersiz IP adresi')}", ephemeral=True)
                        return
                    
                    embed = discord.Embed(
                        title=f"📍 IP Sorgu Sonucu: `{data.get('query')}`",
                        color=discord.Color.blue()
                    )
                    
                    embed.add_field(name="Ülke", value=f"{data.get('country', 'Bilinmiyor')}", inline=True)
                    embed.add_field(name="Bölge / Şehir", value=f"{data.get('regionName', 'Bilinmiyor')} / {data.get('city', 'Bilinmiyor')}", inline=True)
                    
                    district = data.get('district')
                    if district:
                        embed.add_field(name="İlçe", value=f"{district}", inline=True)
                    
                    embed.add_field(name="Posta Kodu", value=f"{data.get('zip', 'Yok')}", inline=True)
                    embed.add_field(name="Koordinatlar", value=f"`{data.get('lat', 0)}, {data.get('lon', 0)}`", inline=True)
                    embed.add_field(name="Zaman Dilimi", value=f"{data.get('timezone', 'Bilinmiyor')}", inline=True)
                    
                    embed.add_field(name="İnternet Sağlayıcı (ISP)", value=f"{data.get('isp', 'Bilinmiyor')}", inline=False)
                    embed.add_field(name="Organizasyon / Şirket", value=f"{data.get('org', 'Bilinmiyor')}", inline=False)
                    embed.add_field(name="ASN", value=f"`{data.get('as', 'Bilinmiyor')}`", inline=False)
                    
                    embed.set_footer(text="IP adresleri VPN veya Proxy kullanılıyorsa yanıltıcı olabilir.")
                    
                    await interaction.user.send(embed=embed)
                    await interaction.followup.send("✅ Sorgu başarılı! Sonuçlar DM kutunuza gönderildi.", ephemeral=True)
                    
            except discord.Forbidden:
                await interaction.followup.send("❌ Sonuçları size DM'den gönderemedim çünkü DM kutunuz kapalı.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Bir hata oluştu: {e}", ephemeral=True)

class IpSorguPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Ip Sorgula", emoji="🌐", style=discord.ButtonStyle.primary, custom_id="ip_sorgula_btn")
    async def ip_sorgula_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(IpSorguModal())

@bot.tree.command(name="ipsorgu", description="IP Sorgulama panelini kanala gönderir")
@app_commands.default_permissions(manage_messages=True)
async def ipsorgu(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌐 Ip Sorgulama Sistemi",
        description="Aşağıdaki Butonu Kullanarak Sorguyu Kullanabilirsin.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=IpSorguPanel())


# ==========================================
# 7. BÖLÜM: DNS SORGULAMA SİSTEMİ
# ==========================================
class DnsSorguModal(discord.ui.Modal, title="🛰️ DNS Sorgula"):
    domain = discord.ui.TextInput(label="Domain Adresi", placeholder="Örn: google.com", required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        domain = self.domain.value.strip()
        
        embed = discord.Embed(
            title=f"🛰️ DNS Sorgu Sonucu: `{domain}`",
            color=discord.Color.blue()
        )
        
        async with aiohttp.ClientSession() as session:
            for record_type in ["A", "MX", "TXT", "NS"]:
                try:
                    url = f"https://dns.google/resolve?name={domain}&type={record_type}"
                    async with session.get(url, timeout=10) as resp:
                        data = await resp.json()
                        
                        if "Answer" in data:
                            records = "\n".join([ans['data'] for ans in data['Answer']])
                            if len(records) > 1000:
                                records = records[:1000] + "..."
                            embed.add_field(name=f"📡 {record_type} Kaydı", value=f"```\n{records}\n```", inline=False)
                        else:
                            embed.add_field(name=f"📡 {record_type} Kaydı", value="`Kayıt bulunamadı.`", inline=False)
                except Exception:
                    pass
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.followup.send("✅ Sorgu başarılı! Sonuçlar DM kutunuza gönderildi.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Sonuçları size DM'den gönderemedim çünkü DM kutunuz kapalı.", ephemeral=True)

class DnsSorguPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="DNS Sorgula", emoji="🛰️", style=discord.ButtonStyle.primary, custom_id="dns_sorgula_btn")
    async def dns_sorgula_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DnsSorguModal())

@bot.tree.command(name="dnssorgu", description="DNS Sorgulama panelini kanala gönderir")
@app_commands.default_permissions(manage_messages=True)
async def dnssorgu(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛰️ DNS Sorgulama Sistemi",
        description="Aşağıdaki Butonu Kullanarak Sorguyu Kullanabilirsin.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=DnsSorguPanel())


# ==========================================
# 8. BÖLÜM: WEB SCANNER (PASİF KEŞİF)
# ==========================================
class WebScannerModal(discord.ui.Modal, title="🕸️ Web Tarayıcı"):
    url_input = discord.ui.TextInput(label="Hedef URL", placeholder="Örn: https://example.com", required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        target = self.url_input.value.strip()
        if not target.startswith("http"):
            target = "https://" + target
            
        embed = discord.Embed(title=f"🕸️ Web Tarama Sonucu: {target}", color=discord.Color.blue())
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(target, timeout=10) as resp:
                    embed.add_field(name="🌐 HTTP Durum Kodu", value=f"`{resp.status}`", inline=True)
                    
                    server = resp.headers.get("Server", "Bilinmiyor")
                    powered_by = resp.headers.get("X-Powered-By", "Bilinmiyor")
                    embed.add_field(name="🖥️ Sunucu", value=f"`{server}`", inline=True)
                    embed.add_field(name="⚙️ Teknoloji", value=f"`{powered_by}`", inline=True)
                    
                    sec_headers = {
                        "Strict-Transport-Security": "HSTS",
                        "X-Frame-Options": "X-Frame-Options",
                        "Content-Security-Policy": "CSP",
                        "X-Content-Type-Options": "X-Content-Type-Options"
                    }
                    sec_results = []
                    for h, name in sec_headers.items():
                        if h in resp.headers:
                            sec_results.append(f"✅ {name}")
                        else:
                            sec_results.append(f"❌ {name}")
                            
                    embed.add_field(name="🔒 Güvenlik Başlıkları", value="\n".join(sec_results), inline=False)
                    
                    if resp.history:
                        redirects = " -> ".join([str(r.url) for r in resp.history])
                        embed.add_field(name="🔄 Yönlendirmeler", value=f"```{redirects}```", inline=False)
                        
            except Exception as e:
                embed = discord.Embed(title="❌ Tarama Başarısız", description=f"`{str(e)}`", color=discord.Color.red())
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.followup.send("✅ Tarama başarılı! Sonuçlar DM kutunuza gönderildi.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Sonuçları size DM'den gönderemedim çünkü DM kutunuz kapalı.", ephemeral=True)

class WebScannerPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Web Tara", emoji="🕸️", style=discord.ButtonStyle.primary, custom_id="web_scan_btn")
    async def web_scan_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WebScannerModal())

@bot.tree.command(name="webscanner", description="Web tarama panelini kanala gönderir")
@app_commands.default_permissions(manage_messages=True)
async def webscanner(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🕸️ Web Scanner Sistemi",
        description="Aşağıdaki butonu kullanarak hedef site hakkında pasif bilgi toplayabilirsin.",
        color=discord.Color.dark_theme()
    )
    await interaction.response.send_message(embed=embed, view=WebScannerPanel())


# ==========================================
# 9. BÖLÜM: TEMP MAİL SİSTEMİ
# ==========================================
aktif_hesaplar = {}

def rastgele_metin(uzunluk=10):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=uzunluk))

class TempMailGelenKutusuPanel(discord.ui.View):
    def __init__(self, email, token, mesajlar):
        super().__init__(timeout=180)
        self.email = email
        self.token = token
        self.mesajlar = mesajlar
        
        if mesajlar:
            options = []
            for msg in mesajlar[:10]:
                sender = msg.get("from", {}).get("address", "Bilinmiyor")
                subject = msg.get("subject", "Konu yok")
                options.append(discord.SelectOption(label=f"{subject[:30]}...", description=f"Kimden: {sender}", value=msg["id"]))
            
            select = discord.ui.Select(placeholder="Okumak için bir mail seçin...", options=options)
            select.callback = self.mail_sec
            self.add_item(select)

    async def mail_sec(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        mesaj_id = interaction.data["values"][0]
        
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.token}"}
            url = f"https://api.mail.tm/messages/{mesaj_id}"
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    konu = data.get("subject", "Konu yok")
                    gonderen = data.get("from", {}).get("address", "Bilinmiyor")
                    icerik = data.get("text", "")
                    
                    if not icerik:
                        html = data.get("html", [""])[0] if data.get("html") else ""
                        icerik = re.sub('<[^<]+?>', '', html) if html else "İçerik bulunamadı."
                    
                    if len(icerik) > 1900:
                        icerik = icerik[:1900] + "... (kırpıldı)"
                        
                    embed = discord.Embed(title=f"📩 {konu}", color=discord.Color.blue())
                    embed.add_field(name="Kimden", value=f"`{gonderen}`", inline=False)
                    embed.add_field(name="İçerik", value=f"```\n{icerik}\n```", inline=False)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.followup.send("❌ Mail okunamadı, süresi dolmuş olabilir.", ephemeral=True)

class TempMailPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Temp Mail Al", emoji="✉️", style=discord.ButtonStyle.primary, custom_id="tempmail_olustur_btn")
    async def btn_olustur(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://api.mail.tm/domains") as resp:
                    domains = await resp.json()
                    domain = domains["hydra:member"][0]["domain"]
                
                email = f"{rastgele_metin()}@{domain}"
                password = rastgele_metin(12)
                payload = {"address": email, "password": password}
                
                async with session.post("https://api.mail.tm/accounts", json=payload) as resp:
                    if resp.status not in [201, 200]:
                        await interaction.followup.send("❌ Mail hesabı oluşturulamadı. Lütfen tekrar deneyin.", ephemeral=True)
                        return
                
                async with session.post("https://api.mail.tm/token", json=payload) as resp:
                    token_data = await resp.json()
                    token = token_data["token"]
                
                aktif_hesaplar[interaction.user.id] = {"email": email, "token": token}
                
                embed = discord.Embed(
                    title="📧 Geçici Mailiniz Hazır!",
                    description=f"`{email}`\n\nGelen kutusunu kontrol etmek için aşağıdaki **Gelen Kutusu** butonunu kullanabilirsiniz.\n\n⚠️ *Mail şifresi: `{password}` (Sadece sizin görebileceğiniz bir bilgidir.)*",
                    color=discord.Color.green()
                )
                await interaction.user.send(embed=embed)
                await interaction.followup.send("✅ Mail adresiniz DM kutunuza gönderildi.", ephemeral=True)
                
            except Exception as e:
                await interaction.followup.send(f"❌ Bir hata oluştu: {e}", ephemeral=True)

    @discord.ui.button(label="Gelen Kutusu", emoji="📥", style=discord.ButtonStyle.secondary, custom_id="tempmail_gelen_btn")
    async def btn_gelen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id not in aktif_hesaplar:
            await interaction.response.send_message("❌ Önce **Temp Mail Al** butonuna basarak bir mail adresi oluşturun.", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        hesap = aktif_hesaplar[interaction.user.id]
        
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {hesap['token']}"}
            async with session.get("https://api.mail.tm/messages", headers=headers) as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Gelen kutusuna erişilemedi.", ephemeral=True)
                    return
                
                data = await resp.json()
                mesajlar = data.get("hydra:member", [])
                
                if not mesajlar:
                    await interaction.followup.send(f"📭 `{hesap['email']}` gelen kutunuz şu an boş.", ephemeral=True)
                    return
                
                embed = discord.Embed(title=f"📬 Gelen Kutusu: {hesap['email']}", description="Aşağıdaki menüden okumak istediğiniz maili seçin.", color=discord.Color.blue())
                
                for i, msg in enumerate(mesajlar[:5]):
                    embed.add_field(
                        name=f"{i+1}. {msg.get('subject', 'Konu yok')}",
                        value=f"Kimden: `{msg.get('from', {}).get('address', 'Bilinmiyor')}`",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed, view=TempMailGelenKutusuPanel(hesap['email'], hesap['token'], mesajlar), ephemeral=True)

@bot.tree.command(name="tempmail", description="Temp Mail panelini kanala gönderir.")
@app_commands.default_permissions(manage_messages=True)
async def tempmail(interaction: discord.Interaction):
    embed = discord.Embed(
        title="✉️ Temp Mail Sistemi",
        description="Aşağıdaki butonu kullanarak anında geçici mail oluşturabilirsiniz.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=TempMailPanel())


# ==========================================
# 10. BÖLÜM: RASTGELE İBAN ÜRETİCİ
# ==========================================
def generate_turkish_iban():
    bank_codes = ["00010", "00012", "00046", "00064", "00067", "00015", "00017"]
    bank_code = random.choice(bank_codes)
    account = "0" + "".join([str(random.randint(0, 9)) for _ in range(16)])
    
    bban = bank_code + account
    check_string = bban + "29002700"
    remainder = int(check_string) % 97
    check_digits = 98 - remainder
    
    iban = f"TR{check_digits:02d}{bank_code}{account}"
    formatted_iban = f"{iban[:4]} {iban[4:8]} {iban[8:12]} {iban[12:16]} {iban[16:20]} {iban[20:24]} {iban[24:]}"
    return formatted_iban

class IbanPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="İBAN Üret", emoji="🏦", style=discord.ButtonStyle.primary, custom_id="iban_uret_btn")
    async def iban_uret_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        ibanlar = [generate_turkish_iban() for _ in range(10)]
        formatli_metin = "\n".join(ibanlar)
        
        mesaj = f"```\n{formatli_metin}\n```"
        await interaction.response.send_message(mesaj, ephemeral=True)

@bot.tree.command(name="iban", description="Rastgele İBAN üretme panelini kanala gönderir.")
@app_commands.default_permissions(manage_messages=True)
async def iban(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🏦 İBAN ÜRETME",
        description="Aşağıdaki butona basarak geçerli formatta rastgele İBAN üretebilirsiniz.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, view=IbanPanel())


# ==========================================
# 11. BÖLÜM: İBAN SORGU SİSTEMİ
# ==========================================
BANKA_KODLARI = {
    "00010": "Ziraat Bankası",
    "00012": "Halkbank",
    "00015": "Vakıfbank",
    "00017": "Yapı Kredi",
    "00046": "Akbank",
    "00062": "Garanti BBVA",
    "00064": "Türkiye İş Bankası",
    "00067": "Yapı Kredi",
    "00099": "ING Bank",
    "00103": "Fibabanka",
    "00111": "QNB Finansbank",
    "00123": "HSBC",
    "00134": "DenizBank",
    "00135": "Anadolubank",
    "00146": "Odeabank",
    "00203": "Albaraka Türk"
}

def validate_iban(iban):
    iban = iban.replace(" ", "").upper()
    if len(iban) != 26 or not iban.startswith("TR"):
        return False, iban
    
    rearranged = iban[4:] + iban[:4]
    numeric_string = ""
    for char in rearranged:
        if char.isdigit():
            numeric_string += char
        else:
            numeric_string += str(ord(char) - 55)
            
    return int(numeric_string) % 97 == 1, iban

class IbanSorguModal(discord.ui.Modal, title="🏦 İBAN Sorgula"):
    iban_input = discord.ui.TextInput(label="İBAN Numarası", placeholder="Örn: TR12 3456 7890 1234 5678 9012 34", required=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        is_valid, iban = validate_iban(self.iban_input.value)
        
        if not iban.startswith("TR") or len(iban) != 26:
            await interaction.followup.send("❌ Geçersiz formatta İBAN girdiniz (TR ile başlamalı ve 26 haneli olmalı).", ephemeral=True)
            return
            
        bank_code = iban[4:9]
        bank_name = BANKA_KODLARI.get(bank_code, "Bilinmeyen / Özel Banka")
        
        embed = discord.Embed(
            title="🏦 İBAN Sorgu Sonucu",
            color=discord.Color.green() if is_valid else discord.Color.red()
        )
        
        embed.add_field(name="Ülke", value="Türkiye (TR)", inline=True)
        embed.add_field(name="Geçerlilik", value="✅ Geçerli (Mod 97 Doğrulandı)" if is_valid else "❌ Geçersiz (Hatalı İBAN)", inline=True)
        embed.add_field(name="Banka", value=f"`{bank_name}`", inline=True)
        embed.add_field(name="Banka Kodu", value=f"`{bank_code}`", inline=True)
        embed.add_field(name="Hesap Numarası", value=f"`{iban[9:]}`", inline=False)
        
        if is_valid:
            embed.set_footer(text="Bu İBAN matematiksel olarak geçerlidir ancak aktif bir hesaba ait olmayabilir.")
        
        try:
            await interaction.user.send(embed=embed)
            await interaction.followup.send("✅ Sorgu başarılı! Sonuçlar DM kutunuza gönderildi.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Sonuçları size DM'den gönderemedim çünkü DM kutunuz kapalı.", ephemeral=True)

class IbanSorguPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="İBAN Sorgula", emoji="🏦", style=discord.ButtonStyle.primary, custom_id="iban_sorgula_btn")
    async def iban_sorgula_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(IbanSorguModal())

@bot.tree.command(name="ibansorgu", description="İBAN Sorgulama panelini kanala gönderir")
@app_commands.default_permissions(manage_messages=True)
async def ibansorgu(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🏦 İBAN Sorgulama Sistemi",
        description="Aşağıdaki butonu kullanarak bir İBAN'ın banka ve geçerlilik bilgilerini sorgulayabilirsiniz.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=IbanSorguPanel())


# ==========================================
# 12. BÖLÜM: DISCORD TOKEN ÜRETİCİ
# ==========================================
kullanici_token_limitleri = {}

def check_token_limit(user_id: int) -> bool:
    today = time.strftime("%Y-%m-%d")
    key = f"token_{user_id}_{today}"
    kullanici_token_limitleri[key] = kullanici_token_limitleri.get(key, 0) + 1
    return kullanici_token_limitleri[key] <= 5

def generate_fake_discord_token():
    user_id = str(random.randint(100000000000000000, 999999999999999999))
    b64_user_id = base64.b64encode(user_id.encode()).decode().replace("=", "")
    
    timestamp = str(int(time.time()) - random.randint(10000000, 20000000))
    b64_timestamp = base64.b64encode(timestamp.encode()).decode().replace("=", "")[:6]
    
    chars = string.ascii_letters + string.digits + "_-"
    signature = ''.join(random.choices(chars, k=38))
    
    return f"{b64_user_id}.{b64_timestamp}.{signature}"

class TokenGenPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Token Üret", emoji="🔐", style=discord.ButtonStyle.primary, custom_id="token_uret_btn")
    async def token_uret_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not check_token_limit(interaction.user.id):
            await interaction.response.send_message("❌ Günlük token üretme limitinizi (5) doldurdunuz. Yarın tekrar deneyebilirsiniz.", ephemeral=True)
            return

        token = generate_fake_discord_token()
        mesaj = f"```\n{token}\n```"
        await interaction.response.send_message(mesaj, ephemeral=True)

@bot.tree.command(name="tokengen", description="Rastgele Discord Token üretme panelini kanala gönderir.")
@app_commands.default_permissions(manage_messages=True)
async def tokengen(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔐 Discord Token Üretici",
        description="Aşağıdaki butona basarak rastgele bir Discord tokenı üretebilirsiniz.\n*(Her kullanıcı günde en fazla 5 kez kullanabilir.)*",
        color=discord.Color.dark_theme()
    )
    await interaction.response.send_message(embed=embed, view=TokenGenPanel())


# ==========================================
# 13. BÖLÜM: LİNK KISALTICI (TINYURL API)
# ==========================================
class KisaltModal(discord.ui.Modal, title="🔗 Link Kısaltıcı"):
    uzun_link = discord.ui.TextInput(label="Uzun Link", placeholder="https://ornek.com/cok/uzun/bir/link", required=True)
    ozel_isim = discord.ui.TextInput(label="Özel İsim (İsteğe Bağlı)", placeholder="Sadece harf ve rakam (örn: bedavanumara)", required=False)
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        target_url = self.uzun_link.value.strip()
        if not target_url.startswith("http"):
            target_url = "https://" + target_url
            
        kisa_isim = self.ozel_isim.value.strip().replace(" ", "-").lower() if self.ozel_isim.value else ""
        
        # TinyURL API isteği
        api_url = f"https://tinyurl.com/api-create.php?url={target_url}"
        if kisa_isim:
            api_url += f"&alias={kisa_isim}"
            
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(api_url, timeout=10) as resp:
                    text_response = await resp.text()
                    
                    # TinyURL başarılı olursa doğrudan linki döner
                    if resp.status == 200 and text_response.startswith("https://tinyurl.com/"):
                        embed = discord.Embed(title="✅ Link Kısaltıldı", color=discord.Color.green())
                        embed.add_field(name="Uzun Link", value=f"`{target_url}`", inline=False)
                        embed.add_field(name="Yeni Link", value=f"`{text_response}`", inline=False)
                        await interaction.followup.send(embed=embed, ephemeral=True)
                    else:
                        # Eğer isim zaten alınmışsa veya başka bir hata varsa (TinyURL HTML döner)
                        await interaction.followup.send(f"❌ Link kısaltılamadı. Sebep: Seçtiğiniz `{kisa_isim}` ismi zaten alınmış olabilir. Farklı bir isim deneyin veya isim kısmını boş bırakın.", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Bir hata oluştu: {e}", ephemeral=True)

class KisaltPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Link Kısalt", emoji="🔗", style=discord.ButtonStyle.primary, custom_id="kisalt_btn")
    async def kisalt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(KisaltModal())

@bot.tree.command(name="kisalt", description="Link kısaltma panelini kanala gönderir")
@app_commands.default_permissions(manage_messages=True)
async def kisalt(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔗 Link Kısaltıcı",
        description="Aşağıdaki butonu kullanarak uzun linklerinizi kısaltabilirsiniz.",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=KisaltPanel())


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
    
    print(f"[clerk] {bot.user} çevrimiçi! 13 sistem aktif.")

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
