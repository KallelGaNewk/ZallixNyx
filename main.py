import math
import os
import discord
import wavelink
from dotenv import load_dotenv
from discord.ext import commands
from cryptography.fernet import Fernet

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

client = commands.Bot(intents=intents, command_prefix=';', help_command=None)
enigma = Fernet(os.getenv('FERNET_KEY').encode())

@client.event
async def on_ready():
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.listening,
            name="music"),
        status=discord.Status.online
    )

    address = os.getenv('LAVALINK_IP')
    port = os.getenv('LAVALINK_PORT')
    password = os.getenv('LAVALINK_PASSWORD')

    if address is None or port is None or password is None:
        print('Lavalink not configured')
        exit(1)

    node = wavelink.Node(uri=f'http://{address}:{port}', password=password)
    back: dict[str, wavelink.Node] = await wavelink.NodePool.connect(client=client, nodes=[node])
    for node in back.values():
        print(f'Connected to Lavalink node {node.id} ({node.uri})')

@client.check
async def block_dms(ctx):
    return ctx.guild is not None

@client.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(content=error, delete_after=5, mention_author=True)
    else:
        print(error)
        encrypted_error = enigma.encrypt(str(error).encode()).decode()
        await ctx.reply(content=f"There's a error. Send this to the developer:\n```Command: {ctx.command.name}\n{encrypted_error}```", mention_author=True)

@client.command(name="decrypt")
async def decrypt_command(ctx: commands.Context, *, text: str):
    if not await client.is_owner(ctx.author):
        return

    try:
        await ctx.reply(f'```{enigma.decrypt(text.encode()).decode()}```')
    except Exception as e:
        await ctx.reply(f'Error: {e}')

@client.command(name="help", aliases=["h"], description="Shows this message")
async def help_command(ctx: commands.Context):
    embed = discord.Embed(
        title="Help",
        description="Here's a list of all commands",
        color=discord.Color.blue()
    )

    for command in client.commands:
        if command.name == 'decrypt':
            continue

        embed.add_field(
            name=f"{client.command_prefix}{command.name} {command.usage if command.usage else ''}",
            value=f"(Aliases: {', '.join(command.aliases)})" if command.aliases else 'None' + f"\n{command.description}",
            inline=False
        )

    await ctx.reply(embed=embed)

@client.command(name="play", aliases=["p"], usage="[query (text)]",  description="Joins on yours voice channel, and play music")
@commands.cooldown(1, 5, commands.BucketType.guild)
async def play(ctx: commands.Context, *, query: str | None):
    if not query:
        return await ctx.reply('Please provide a search query.')

    if ctx.voice_client:
        if ctx.author.voice.channel.id == ctx.voice_client.channel.id:
            vc: wavelink.Player = ctx.voice_client
        else:
            return await ctx.reply("You aren't connected to the same voice channel")
    else:
        if ctx.author.voice:
            vc: wavelink.Player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
        else:
            return await ctx.reply("You aren't connected to a voice channel")

    tracks = await wavelink.GenericTrack.search(query) or await wavelink.YouTubeTrack.search(query)
    if not tracks:
        return await ctx.reply(f'Track search failed for `{query}`')

    track = tracks[0]

    if not vc.is_playing():
        await vc.play(track, populate=True)
        vc.autoplay = True
        await ctx.reply(f'Now playing `{track.title}` by `{track.author}`!')
    else:
        await vc.queue.put_wait(track)
        await ctx.reply(f'Added `{track.title}` by `{track.author}` on the queue.')

@client.command(name="forceplay", aliases=["fp"], usage="[query (text)]", description="Forces playing a music, stopping the current track")
@commands.cooldown(1, 5, commands.BucketType.guild)
async def forceplay(ctx: commands.Context, *, query: str | None):
    if not query:
        return await ctx.reply('Please provide a search query.')

    if ctx.voice_client:
        if ctx.author.voice.channel.id == ctx.voice_client.channel.id:
            vc: wavelink.Player = ctx.voice_client
        else:
            return await ctx.reply("You aren't connected to the same voice channel")
    else:
        if ctx.author.voice:
            vc: wavelink.Player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
        else:
            return await ctx.reply("You aren't connected to a voice channel")

    tracks = await wavelink.GenericTrack.search(query) or await wavelink.YouTubeTrack.search(query)
    if not tracks:
        return await ctx.reply(f'Track search failed for `{query}`')

    track = tracks[0]

    await vc.play(track, populate=True)
    await ctx.reply(f'Queue cleared, now playing `{track.title}` by `{track.author}`!')

@client.command(name="nowplaying", aliases=["np"], description="What is playing now?")
async def nowplaying(ctx: commands.Context):
    if not ctx.voice_client:
        return await ctx.reply("I'm not connected to a voice channel")

    if not ctx.voice_client.is_playing():
        return await ctx.reply("I'm not playing anything")

    track: wavelink.GenericTrack = ctx.voice_client.current

    if not track:
        return await ctx.reply("I'm not playing anything")

    embed = discord.Embed(
        description=f"[`{track.title}`]({track.uri}) by `{track.author}`",
        color=ctx.me.accent_color or ctx.me.color
    )

    await ctx.reply(embed=embed)

@client.command(name="queue", aliases=["q"], usage="[page (number)]", description="View the entire queue list of tracks you loaded")
async def queue(ctx: commands.Context, page: int | None = 1):
    if not ctx.voice_client:
        return await ctx.reply("I'm not connected to a voice channel")

    if not ctx.voice_client.is_playing():
        return await ctx.reply("I'm not playing anything")

    if not ctx.voice_client.queue:
        return await ctx.reply("The queue is empty")

    queue = ctx.voice_client.queue
    current_track = ctx.voice_client.current
    embed = discord.Embed(color=ctx.me.color).set_author(
        name=f"Playlist for {ctx.guild.name}",
        icon_url=ctx.guild.icon.url if ctx.guild.icon else ctx.me.avatar.url
    )

    items_per_page = 10
    end = page * items_per_page
    start = end - items_per_page
    tracks = queue[start:end]

    embed.add_field(
        name="Current",
        value=f"[{current_track.title}]({current_track.uri}) by `{current_track.author}`",
        inline=False
    )

    if not tracks:
        embed.description = "No tracks in queue." if page == 1 else "No tracks in this page."
    else:
        embed.description = "\n".join(
            f"{start + i + 1} - [{t.title}]({t.uri}) by `{t.author}`"
            for i, t in enumerate(tracks)
        )

    max_pages = math.ceil(len(queue) / items_per_page)
    embed.set_footer(text=f"Page {page} of {max_pages or 1}")
    await ctx.reply(embed=embed)

@client.command(name="shuffle", aliases=["sh"], description="Randomizes the queue list")
async def shuffle(ctx: commands.Context):
    if not ctx.voice_client:
        return await ctx.reply("I'm not connected to a voice channel")

    if not ctx.voice_client.is_playing():
        return await ctx.reply("I'm not playing anything")

    if not ctx.voice_client.queue:
        return await ctx.reply("The queue is empty")

    ctx.voice_client.queue.shuffle()
    await ctx.reply("Queue shuffled")

@client.command(name="stop", aliases=["leave", "die", "exit", "destroy"], description="Leaves the channel and destroys the player")
async def stop(ctx: commands.Context):
    if not ctx.voice_client:
        return await ctx.reply("I'm not connected to a voice channel")

    await ctx.voice_client.disconnect(force=True)
    await ctx.reply("Player destroyed")

@client.command(name="skip", aliases=["s", "next"], description="Skips the current track")
async def skip(ctx: commands.Context):
    if not ctx.voice_client:
        return await ctx.reply("I'm not connected to a voice channel")

    if not ctx.voice_client.is_playing():
        return await ctx.reply("I'm not playing anything")

    if ctx.author.voice.channel.id != ctx.voice_client.channel.id:
        return await ctx.reply("You aren't connected to the same voice channel")

    track = ctx.voice_client.current
    ctx.voice_client.stop()
    await ctx.reply(f"Skipped `{track.title}`.")

@client.command(name="pause", description="Pauses the current track")
async def pause(ctx: commands.Context):
    if not ctx.voice_client:
        return await ctx.reply("I'm not connected to a voice channel")

    if not ctx.voice_client.is_playing():
        return await ctx.reply("I'm not playing anything")

    if ctx.author.voice.channel.id != ctx.voice_client.channel.id:
        return await ctx.reply("You aren't connected to the same voice channel")

    ctx.voice_client.pause()
    await ctx.reply("Paused!")

@client.command(name="resume", description="Resumes the current track")
async def resume(ctx: commands.Context):
    if not ctx.voice_client:
        return await ctx.reply("I'm not connected to a voice channel")

    if not ctx.voice_client.is_paused():
        return await ctx.reply("I'm not paused")

    if ctx.author.voice.channel.id != ctx.voice_client.channel.id:
        return await ctx.reply("You aren't connected to the same voice channel")

    ctx.voice_client.resume()
    await ctx.reply("Resumed!")

@client.command(name="loop", aliases=["repeat"], usage="[forQueue? (true/false)]", description="Loops the current track")
async def loop(ctx: commands.Context, forQueue: bool = False):
    if not ctx.voice_client:
        return await ctx.reply("I'm not connected to a voice channel")

    if not ctx.voice_client.is_playing():
        return await ctx.reply("I'm not playing anything")

    if ctx.author.voice.channel.id != ctx.voice_client.channel.id:
        return await ctx.reply("You aren't connected to the same voice channel")

    if forQueue:
        if not ctx.voice_client.queue:
            return await ctx.reply("The queue is empty")

        if ctx.voice_client.queue.loop:
            ctx.voice_client.queue.loop = False
            await ctx.reply("Disabled track looping!")

        ctx.voice_client.queue.loop_all = not ctx.voice_client.queue.loop_all
        await ctx.reply(f"Looping {'enabled' if ctx.voice_client.queue.loop_all else 'disabled'} for the queue")
    else:
        ctx.voice_client.queue.loop = not ctx.voice_client.queue.loop
        await ctx.reply(f"Looping {'enabled' if ctx.voice_client.queue.loop else 'disabled'} for this track")

token = os.getenv('DISCORD_TOKEN')

if token is None:
    print('Token not found')
    exit(1)
else:
    client.run(token)
