from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from .models import CustomUser, Profile, CollectedData, Transaction, ReferralBonus, Network, Data_price, Withdrawal


@admin.register(CustomUser)
class CustomUserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Extra Fields', {'fields': ('phone', 'wallet', 'referral_code', 'referred_by')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Extra Fields', {'fields': ('phone', 'wallet')}),
    )
    readonly_fields = ('referral_code',)
    raw_id_fields = ('referred_by',)
    list_display = ('username', 'email', 'referral_code', 'referred_by', 'wallet', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'date_joined')
    search_fields = ('username', 'email', 'referral_code')


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'wallet')

@admin.register(Data_price)
class Data_priceAdmin(admin.ModelAdmin):
    list_display = ('Duration', 'network', 'price','size')

@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    list_display = ('name',)

@admin.register(CollectedData)
class CollectedDataAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'city', 'state', 'country')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'service', 'amount', 'status', 'created_at')
    list_filter = ('service', 'status', 'created_at')
    search_fields = ('user__username', 'description')
    date_hierarchy = 'created_at'


@admin.register(ReferralBonus)
class ReferralBonusAdmin(admin.ModelAdmin):
    list_display = ('beneficiary', 'source_user', 'level', 'percentage', 'amount', 'created_at')
    list_filter = ('level', 'created_at')
    search_fields = ('beneficiary__username', 'source_user__username')
    date_hierarchy = 'created_at'
@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username',)
