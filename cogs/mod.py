import discord
import re
import asyncio

from discord.ext import commands
from utils import permissions, default
from discord.ext.commands import has_permissions
from discord.ext.commands import MissingPermissions, BadArgument


# Source: https://github.com/Rapptz/RoboDanny/blob/rewrite/cogs/mod.py
class MemberID(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            m = await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                return int(argument, base=10)
            except ValueError:
                raise commands.BadArgument(f"{argument} is not a valid member or member ID.") from None
        else:
            return m.id

class ActionReason(commands.Converter):
    async def convert(self, ctx, argument):
        ret = argument

        if len(ret) > 512:
            reason_max = 512 - len(ret) - len(argument)
            raise commands.BadArgument(f"reason is too long ({len(argument)}/{reason_max})")
        return ret


class Moderator(commands.Cog):
    """Discord Admin/Mod Commands"""
    def __init__(self, bot):
        self.bot = bot
        self.config = default.config()

    @commands.command()
    @commands.guild_only()
    @permissions.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = None):
        """ Kicks a user from the current server. """
        if await permissions.check_priv(ctx, member):
            return

        try:
            await member.kick(reason=default.responsible(ctx.author, reason))
            await ctx.send(default.actionmessage("kicked"))
        except Exception as e:
            await ctx.send(e)

    @commands.command(aliases=["nick"])
    @commands.guild_only()
    @permissions.has_permissions(manage_nicknames=True)
    async def nickname(self, ctx, member: discord.Member, *, name: str = None):
        """ Nicknames a user from the current server. """
        if await permissions.check_priv(ctx, member):
            return

        try:
            await member.edit(nick=name, reason=default.responsible(ctx.author, "Changed by command"))
            message = f"Changed **{member.name}'s** nickname to **{name}**"
            if name is None:
                message = f"Reset **{member.name}'s** nickname"
            await ctx.send(message)
        except Exception as e:
            await ctx.send(e)

    @commands.command()
    @commands.guild_only()
    @permissions.has_permissions(ban_members=True)
    async def ban(self, ctx, member: MemberID, *, reason: str = None):
        """ Bans a user from the current server. """
        m = ctx.guild.get_member(member)
        if m is not None and await permissions.check_priv(ctx, m):
            return

        try:
            await ctx.guild.ban(discord.Object(id=member), reason=default.responsible(ctx.author, reason))
            await ctx.send(default.actionmessage("banned"))
        except Exception as e:
            await ctx.send(e)

    @commands.command()
    @commands.guild_only()
    @commands.max_concurrency(1, per=commands.BucketType.user)
    @permissions.has_permissions(ban_members=True)
    async def massban(self, ctx, reason: ActionReason, *members: MemberID):
        """ Mass bans multiple members from the server. """
        try:
            for member_id in members:
                await ctx.guild.ban(discord.Object(id=member_id), reason=default.responsible(ctx.author, reason))
            await ctx.send(default.actionmessage("massbanned", mass=True))
        except Exception as e:
            await ctx.send(e)

    @commands.command()
    @commands.guild_only()
    @permissions.has_permissions(ban_members=True)
    async def unban(self, ctx, member: MemberID, *, reason: str = None):
        """ Unbans a user from the current server. """
        try:
            await ctx.guild.unban(discord.Object(id=member), reason=default.responsible(ctx.author, reason))
            await ctx.send(default.actionmessage("unbanned"))
        except Exception as e:
            await ctx.send(e)

    @commands.command()
    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True, ban_members=True)
    async def mute(self, ctx, member: discord.Member, *, reason: str = None):
        """ Mutes a user from the current server. """
        if await permissions.check_priv(ctx, member):
            return

        muted_role = next((g for g in ctx.guild.roles if g.name == "Muted"), None)

        if not muted_role:
            return await ctx.send("Are you sure you've made a role called **Muted**? Remember that it's case sensitive too...")

        try:
            await member.add_roles(muted_role, reason=default.responsible(ctx.author, reason))
            await ctx.send(default.actionmessage("muted"))
        except Exception as e:
            await ctx.send(e)

    @commands.command()
    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = None):
        """ Unmutes a user from the current server. """
        if await permissions.check_priv(ctx, member):
            return

        muted_role = next((g for g in ctx.guild.roles if g.name == "Muted"), None)

        if not muted_role:
            return await ctx.send("Are you sure you've made a role called **Muted**? Remember that it's case sensitive too...")

        try:
            await member.remove_roles(muted_role, reason=default.responsible(ctx.author, reason))
            await ctx.send(default.actionmessage("unmuted"))
        except Exception as e:
            await ctx.send(e)

    @commands.command(aliases=["ar"])
    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True)
    async def announcerole(self, ctx, *, role: discord.Role):
        """ Makes a role mentionable and removes it whenever you mention the role """
        if role == ctx.guild.default_role:
            return await ctx.send("To prevent abuse, I won't allow mentionable role for everyone/here role.")

        if ctx.author.top_role.position <= role.position:
            return await ctx.send("It seems like the role you attempt to mention is over your permissions, therefore I won't allow you.")

        if ctx.me.top_role.position <= role.position:
            return await ctx.send("This role is above my permissions, I can't make it mentionable ;-;")

        await role.edit(mentionable=True, reason=f"[ {ctx.author} ] announcerole command")
        msg = await ctx.send(f"**{role.name}** is now mentionable, if you don't mention it within 30 seconds, I will revert the changes.")

        while True:
            def role_checker(m):
                if (role.mention in m.content):
                    return True
                return False

            try:
                checker = await self.bot.wait_for("message", timeout=30.0, check=role_checker)
                if checker.author.id == ctx.author.id:
                    await role.edit(mentionable=False, reason=f"[ {ctx.author} ] announcerole command")
                    return await msg.edit(content=f"**{role.name}** mentioned by **{ctx.author}** in {checker.channel.mention}")
                    break
                else:
                    await checker.delete()
            except asyncio.TimeoutError:
                await role.edit(mentionable=False, reason=f"[ {ctx.author} ] announcerole command")
                return await msg.edit(content=f"**{role.name}** was never mentioned by **{ctx.author}**...")
                break

    @commands.group()
    @commands.guild_only()
    @permissions.has_permissions(ban_members=True)
    async def find(self, ctx):
        """ Finds a user within your search term """
        if ctx.invoked_subcommand is None:
            await ctx.send_help(str(ctx.command))

    @find.command(name="playing")
    async def find_playing(self, ctx, *, search: str):
        loop = []
        for i in ctx.guild.members:
            if i.activities and (not i.bot):
                for g in i.activities:
                    if g.name and (search.lower() in g.name.lower()):
                        loop.append(f"{i} | {type(g).__name__}: {g.name} ({i.id})")

        await default.prettyResults(
            ctx, "playing", f"Found **{len(loop)}** on your search for **{search}**", loop
        )

    @find.command(name="username", aliases=["name"])
    async def find_name(self, ctx, *, search: str):
        loop = [f"{i} ({i.id})" for i in ctx.guild.members if search.lower() in i.name.lower() and not i.bot]
        await default.prettyResults(
            ctx, "name", f"Found **{len(loop)}** on your search for **{search}**", loop
        )

    @find.command(name="nickname", aliases=["nick"])
    async def find_nickname(self, ctx, *, search: str):
        loop = [f"{i.nick} | {i} ({i.id})" for i in ctx.guild.members if i.nick if (search.lower() in i.nick.lower()) and not i.bot]
        await default.prettyResults(
            ctx, "name", f"Found **{len(loop)}** on your search for **{search}**", loop
        )

    @find.command(name="id")
    async def find_id(self, ctx, *, search: int):
        loop = [f"{i} | {i} ({i.id})" for i in ctx.guild.members if (str(search) in str(i.id)) and not i.bot]
        await default.prettyResults(
            ctx, "name", f"Found **{len(loop)}** on your search for **{search}**", loop
        )

    @find.command(name="discriminator", aliases=["discrim"])
    async def find_discriminator(self, ctx, *, search: str):
        if not len(search) == 4 or not re.compile("^[0-9]*$").search(search):
            return await ctx.send("You must provide exactly 4 digits")

        loop = [f"{i} ({i.id})" for i in ctx.guild.members if search == i.discriminator]
        await default.prettyResults(
            ctx, "discriminator", f"Found **{len(loop)}** on your search for **{search}**", loop
        )

    @commands.command()
    @commands.guild_only()
    @permissions.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount = 1):
        try:
            amount = int(amount)
        except:
            await ctx.send("Provide an integer amount of messages!")
            return 
        await ctx.channel.purge(limit = amount)

    @purge.error
    async def clear_error(self, ctx, error):
        if isinstance(error, MissingPermissions):
            embed = discord.Embed(title = "Purge Failed!", color = ctx.author.color)
            embed.add_field(name = "Reason:", value = f"`Manage Messages Permissions Missing!`")
            embed.set_footer(text = "Imagine thinking you have the perms!")
            embed.set_author(name = ctx.author.name, icon_url = ctx.author.avatar_url)
            await ctx.send(embed = embed)
        if isinstance(error, commands.BotMissingPermissions):
            em = discord.Embed(title = f'{ctx.command.name} Failed!', color = discord.Color.random(), description = "Ladies and gentlemen we got ||...||")
            em.add_field(name = 'Reason', value = 'I don\'t have the perms to do that-')
            em.add_field(name = 'What to do:', value = "Give me perms when?")
            em.set_footer(text = "-_-", icon_url = ctx.author.avatar_url)
            await ctx.send(embed = em)

    @commands.command()
    async def amiadmin(self, ctx):
        """ Are you an admin? """
        if ctx.author.id in self.config["devperms"]:
            return await ctx.send(f"Yes **{ctx.author.name}** you are an admin! ✅")
            
    
def setup(bot):
    bot.add_cog(Moderator(bot))
