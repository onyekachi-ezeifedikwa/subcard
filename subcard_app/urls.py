from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('referral-dashboard/', views.referral_dashboard_view, name='referral_dashboard'),
    path('api/data-plans/', views.data_plans_json, name='data_plans_json'),
    path('purchase/data/', views.purchase_data_view, name='purchase_data_view'),
    path('purchase/airtime/', views.purchase_airtime_view, name='purchase_airtime'),
    path('webhook/smeplug/', views.smeplug_webhook, name='smeplug_webhook'),
    path('virtual-account/create/', views.create_virtual_account, name='create_virtual_account'),
    path('settings/profile/update/', views.update_profile, name='update_profile'),
    path('settings/password/update/', views.update_password, name='update_password'),
    path('settings/transaction-pin/update/', views.update_transaction_pin, name='update_transaction_pin'),


    
    # Email verification
    path('verify-email/<str:token>/', views.verify_email_view, name='verify_email'),
    path('resend-verification/', views.resend_verification_email, name='resend_verification'),
    
    # Cable TV
    path('cable-tv/', views.cable_tv_view, name='cable_tv'),
    path('api/cable-plans/', views.get_cable_plans, name='get_cable_plans'),
    path('api/validate-smartcard/', views.validate_smart_card_view, name='validate_smart_card'),
    path('purchase/cable/', views.purchase_cable_view, name='purchase_cable'),

    # ── Custom Admin Panel ──────────────────────────────────────────
    path('admin-login/', views.admin_login_view, name='admin_login'),
    path('admin-logout/', views.admin_logout_view, name='admin_logout'),
    path('admin-panel/', views.admin_view, name='admin_panel'),
    path('testadmin/', views.mypannel, name='mypannel'),

    # Admin API — users
    path('admin-api/user/update/', views.admin_update_user, name='admin_update_user'),
    path('admin-api/user/add/', views.admin_add_user, name='admin_add_user'),
    path('admin-api/user/delete/', views.admin_delete_user, name='admin_delete_user'),
    path('admin-api/user/fund-wallet/', views.admin_fund_wallet, name='admin_fund_wallet'),

    # Admin API — transactions
    path('admin-api/transaction/<int:transaction_id>/receipt/', views.admin_transaction_receipt, name='admin_transaction_receipt'),
    path('admin-api/transaction/delete/', views.admin_delete_transaction, name='admin_delete_transaction'),

    # Admin API — data plans
    path('admin-api/data-price/update/', views.admin_update_data_price, name='admin_update_data_price'),
    path('admin-api/data-price/add/', views.admin_add_data_price, name='admin_add_data_price'),
    path('admin-api/data-price/delete/', views.admin_delete_data_price, name='admin_delete_data_price'),

    # Admin API — referrals
    path('admin-api/referral/update/', views.admin_update_referral, name='admin_update_referral'),
    path('admin-api/referral/delete/', views.admin_delete_referral, name='admin_delete_referral'),
    path('admin-api/referral/withdrawal/<int:withdrawal_id>/', views.admin_handle_withdrawal, name='admin_handle_withdrawal'),

    # Reports & Settings API
    path('admin-api/settings/update/', views.admin_update_settings, name='admin_update_settings'),
    path('admin-api/broadcast/send/', views.admin_send_broadcast, name='admin_send_broadcast'),
    path('admin-api/account/update/', views.admin_update_account, name='admin_update_account'),
    path('admin-api/report/export/', views.admin_export_csv, name='admin_export_csv'),
    path('admin-api/payment-methods/update/', views.admin_update_payment_methods, name='admin_update_payment_methods'),
    
    # API Provider Settings & Network Routing Routing
    path('admin-api/api-provider/save/', views.admin_save_api_provider, name='admin_save_api_provider'),
    path('admin-api/api-provider/delete/', views.admin_delete_api_provider, name='admin_delete_api_provider'),
    path('admin-api/network-routing/save/', views.admin_save_network_routing, name='admin_save_network_routing'),

    # ── Payment & Webhooks ──────────────────────────────────────────
    path('payment/dynamic-va/create/', views.request_dynamic_va, name='request_dynamic_va'),
    path('webhook/katpay/', views.katpay_webhook, name='katpay_webhook'),
    path('referral/withdraw/', views.withdraw_referral_to_wallet, name='withdraw_referral'),
    path('referral/request-payout/', views.request_withdrawal_payout, name='request_withdrawal_payout'),
    # Maintenance page
    path('maintenance/', views.maintenance_view, name='maintenance'),

    # Password reset
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='subcard_app/password_reset.html',
        subject_template_name='subcard_app/password_reset_subject.txt',
        email_template_name='subcard_app/password_reset_email.txt',
        html_email_template_name='subcard_app/password_reset_email.html'
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='subcard_app/password_reset_done.html'), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='subcard_app/password_reset_confirm.html'), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(template_name='subcard_app/password_reset_complete.html'), name='password_reset_complete'),
]
