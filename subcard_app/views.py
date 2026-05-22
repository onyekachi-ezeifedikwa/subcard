import json
import time
import requests
from decimal import Decimal
from django.db import models
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .models import Profile, CollectedData, Transaction, ReferralBonus, Network, Data_price, CustomUser, SiteSetting, DynamicVirtualAccount, CableProvider, CablePlan, CableSubscription, Withdrawal, APIProvider
from .cable_api import get_cable_providers, validate_smart_card, validate_meter, purchase_cable_subscription
import csv
from .sme_plug import (
    get_data_plans, purchase_data, purchase_airtime,
    get_transaction, SMEPlugAPIError, generate_reference,
)
from .panel import transact_failed_count, total_transact_success,total_transact_success_today,user_count,active_user,sales
from .katpay import (
    create_static_virtual_account, create_dynamic_virtual_account,
    KatpayAPIError, generate_reference as katpay_generate_reference,
)
import hmac
import hashlib
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.utils.html import strip_tags
from django.template.loader import render_to_string
from django.conf import settings as django_settings

User = get_user_model()

NETWORK_MAP = {
    'mtn': 1,
    'airtel': 2,
    'glo': 4,
    '9mobile': 3,
}





def validate_transaction_pin(request):
    """Utility to validate PIN during POST requests."""
    pin = request.POST.get('transaction_pin')
    if not request.user.transaction_pin:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return JsonResponse({'success': False, 'error': 'No PIN set'}, status=403)
        messages.warning(request, "Please set a Transaction PIN before making purchases.")
        return redirect('dashboard')
        
    if not request.user.check_transaction_pin(pin):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return JsonResponse({'success': False, 'error': 'Invalid PIN'}, status=403)
        messages.error(request, "Invalid Transaction PIN.")
        return redirect('dashboard')
    return None

@login_required
@require_POST
def update_transaction_pin(request):
    """Create or update the user's transaction PIN."""
    current_pin = request.POST.get('current_pin')
    new_pin = request.POST.get('new_pin')
    confirm_pin = request.POST.get('confirm_pin')
    
    if request.user.transaction_pin and not request.user.check_transaction_pin(current_pin):
        messages.error(request, "Current PIN is incorrect.")
        return redirect('dashboard')
        
    if not new_pin or len(new_pin) < 4:
        messages.error(request, "PIN must be at least 4 digits.")
        return redirect('dashboard')
        
    if new_pin != confirm_pin:
        messages.error(request, "New PINs do not match.")
        return redirect('dashboard')
        
    request.user.set_transaction_pin(new_pin)
    messages.success(request, "Transaction PIN updated successfully.")
    return redirect('dashboard')


def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            # Check if user exists but is inactive
            potential_user = User.objects.filter(username=username).first()
            if potential_user and not potential_user.is_active:
                messages.error(request, 'Your account is not active. Please check your email for a verification link.')
            else:
                messages.error(request, 'Invalid username or password.')
    return render(request, 'subcard_app/login.html')


def admin_login_view(request):
    """Separate login for the admin panel."""
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin_panel')
        
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_staff:
                login(request, user)
                return redirect('admin_panel')
            else:
                messages.error(request, 'Access denied. Staff only.')
        else:
            messages.error(request, 'Invalid admin credentials.')
            
    return render(request, 'subcard_app/admin_login.html')


def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        phone = request.POST.get('phone')
        referral_code = request.POST.get('referral_code', '').strip()

        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'subcard_app/register.html')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'subcard_app/register.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists.')
            return render(request, 'subcard_app/register.html')

        referrer = None
        if referral_code:
            try:
                referrer = User.objects.get(referral_code=referral_code)
            except User.DoesNotExist:
                messages.error(request, 'Invalid referral code.')
                return render(request, 'subcard_app/register.html')

        user = User.objects.create_user(
            username=username, email=email, password=password,
            referred_by=referrer
        )
        user.phone = phone
        user.is_active = False # Require email verification
        user.save()
        Profile.objects.create(user=user, phone=phone)
        
        # Send email verification
        send_verification_email(request, user)
        
        messages.success(request, 'Account created successfully. Please check your email to verify your account.')
        return redirect('login')

    return render(request, 'subcard_app/register.html')


def send_verification_email(request, user):
    """Send email verification to user"""
    try:
        subject = 'Verify Your Email Address'
        verification_url = f"{request.scheme}://{request.get_host()}/verify-email/{user.email_verification_token}/"
        
        html_message = render_to_string('subcard_app/email_verification.html', {
            'user': user,
            'verification_url': verification_url,
        })
        
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject,
            plain_message,
            django_settings.DEFAULT_FROM_EMAIL,
            [user.email],
            html_message=html_message,
            fail_silently=False,
        )
        
        user.email_verification_sent_at = timezone.now()
        user.save()
        
    except Exception as e:
        messages.error(request, f'Failed to send verification email: {str(e)}')


def verify_email_view(request, token):
    """Verify user email address"""
    try:
        user = User.objects.get(email_verification_token=token)
        user.is_email_verified = True
        user.is_active = True # Activate account
        user.save()
        
        messages.success(request, 'Email verified successfully! You can now login.')
        return redirect('login')
        
    except User.DoesNotExist:
        messages.error(request, 'Invalid verification token.')
        return redirect('login')


@login_required
def resend_verification_email(request):
    """Resend verification email to the logged-in user."""
    user = request.user
    if user.is_email_verified:
        messages.info(request, 'Your email is already verified.')
        return redirect('dashboard')
    
    # Check if a verification email was sent recently (throttle)
    if user.email_verification_sent_at:
        from django.utils.timezone import now
        from datetime import timedelta
        if now() < user.email_verification_sent_at + timedelta(minutes=5):
            messages.warning(request, 'Please wait at least 5 minutes before requesting another verification email.')
            return redirect('dashboard')
            
    send_verification_email(request, user)
    messages.success(request, 'Verification email has been resent. Please check your inbox.')
    return redirect('dashboard')


def maintenance_view(request):
    """Render the maintenance page."""
    return render(request, 'subcard_app/maintenance_page.html')


@login_required
def cable_tv_view(request):
    """Cable TV subscription page"""
    if not request.user.is_email_verified:
        messages.error(request, 'Please verify your email to access cable TV services.')
        return redirect('dashboard')
    
    providers = CableProvider.objects.filter(is_active=True)
    context = {
        'providers': providers,
    }
    return render(request, 'subcard_app/cable_tv.html', context)


@login_required
def get_cable_plans(request):
    """Get cable TV plans for a provider"""
    provider_id = request.GET.get('provider_id')
    if not provider_id:
        return JsonResponse({'success': False, 'error': 'Provider ID required'})
    
    try:
        provider = CableProvider.objects.get(id=provider_id, is_active=True)
        plans = CablePlan.objects.filter(provider=provider, is_active=True)
        
        plans_data = []
        for plan in plans:
            plans_data.append({
                'id': plan.id,
                'name': plan.name,
                'code': plan.code,
                'price': float(plan.price),
                'duration': plan.duration,
            })
        
        return JsonResponse({'success': True, 'plans': plans_data})
    except CableProvider.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Provider not found'})


@login_required
def validate_smart_card_view(request):
    """Validate smart card number"""
    smart_card_number = request.GET.get('smart_card_number')
    provider_code = request.GET.get('provider_code')
    
    if not smart_card_number or not provider_code:
        return JsonResponse({'success': False, 'error': 'Smart card number and provider required'})
    
    result = validate_smart_card(smart_card_number, provider_code)
    return JsonResponse(result)


@login_required
def purchase_cable_view(request):
    """Purchase cable TV subscription"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})
    
    if not request.user.is_email_verified:
        return JsonResponse({'success': False, 'error': 'Email not verified'})
    
    provider_id = request.POST.get('provider_id')
    plan_id = request.POST.get('plan_id')
    smart_card_number = request.POST.get('smart_card_number')
    
    if not all([provider_id, plan_id, smart_card_number]):
        return JsonResponse({'success': False, 'error': 'All fields required'})
        
    # PIN Validation
    pin_error = validate_transaction_pin(request)
    if pin_error:
        return pin_error

    
    try:
        provider = CableProvider.objects.get(id=provider_id, is_active=True)
        plan = CablePlan.objects.get(id=plan_id, provider=provider, is_active=True)
        
        # Check user wallet balance
        if request.user.wallet < plan.price:
            return JsonResponse({'success': False, 'error': 'Insufficient wallet balance'})
        
        # Generate customer reference
        customer_ref = f"CABLE{request.user.id}{timezone.now().strftime('%Y%m%d%H%M%S')}"
        
        # Create subscription record
        subscription = CableSubscription.objects.create(
            user=request.user,
            provider=provider,
            plan=plan,
            smart_card_number=smart_card_number,
            customer_reference=customer_ref,
            amount=plan.price,
            status='processing'
        )
        
        # Deduct from wallet
        request.user.wallet -= plan.price
        request.user.save()
        
        # Process API purchase
        api_result = purchase_cable_subscription(
            smart_card_number, 
            provider.code, 
            plan.code, 
            customer_ref
        )
        
        # Update subscription based on API result
        if api_result.get('success'):
            subscription.status = 'success'
            subscription.api_response = json.dumps(api_result)
            subscription.save()
            
            # Create transaction record
            Transaction.objects.create(
                user=request.user,
                service='cable',
                amount=plan.price,
                description=f"{provider.name} - {plan.name}",
                status='success',
                customer_reference=customer_ref,
                phone=smart_card_number,
                plan_id=plan.code,
                network_id=provider.id
            )
            
            return JsonResponse({
                'success': True, 
                'message': 'Cable subscription successful!',
                'reference': customer_ref
            })
        else:
            # Refund wallet on failure
            request.user.wallet += plan.price
            request.user.save()
            
            subscription.status = 'failed'
            subscription.api_response = json.dumps(api_result)
            subscription.save()
            
            return JsonResponse({
                'success': False, 
                'error': api_result.get('error', 'Subscription failed')
            })
            
    except (CableProvider.DoesNotExist, CablePlan.DoesNotExist):
        return JsonResponse({'success': False, 'error': 'Invalid provider or plan'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def request_withdrawal_payout(request):
    amount = request.POST.get('amount')
    payout_method = request.POST.get('method')
    bank_name = request.POST.get('bank_name', '')
    account_number = request.POST.get('account_number', '')
    account_name = request.POST.get('account_name', '')
    phone_number = request.POST.get('phone', '')
    network = request.POST.get('network', '')

    if not amount:
        return JsonResponse({'success': False, 'error': 'Amount is required'})

    try:
        amount = Decimal(amount)
        if amount < 500 or amount > 8500:
            return JsonResponse({'success': False, 'error': 'Amount must be between ₦500 and ₦8,500'})
    except:
        return JsonResponse({'success': False, 'error': 'Invalid amount'})

    if request.user.referral_wallet < amount:
        return JsonResponse({'success': False, 'error': 'Insufficient referral balance'})

    # PIN Validation
    pin_error = validate_transaction_pin(request)
    if pin_error:
        return pin_error

    # Create withdrawal request
    Withdrawal.objects.create(
        user=request.user,
        amount=amount,
        payout_method=payout_method,
        bank_name=bank_name,
        account_number=account_number,
        account_name=account_name,
        phone_number=phone_number,
        network=network,
        status='pending'
    )

    # Deduct from referral wallet
    request.user.referral_wallet -= amount
    request.user.save()

    # Send email to admin
    try:
        subject = 'New Withdrawal Request'
        message = f"User {request.user.username} has requested a withdrawal of ₦{amount} via {payout_method}."
        # If ADMINS is not set, we'll try to send to superusers
        admin_emails = [admin[1] for admin in getattr(django_settings, 'ADMINS', [])]
        if not admin_emails:
            admin_emails = list(User.objects.filter(is_superuser=True).values_list('email', flat=True))
            
        if admin_emails:
            send_mail(
                subject,
                message,
                django_settings.DEFAULT_FROM_EMAIL,
                admin_emails,
                fail_silently=True,
            )
    except Exception as e:
        print(f"Error sending withdrawal email: {e}")

    return JsonResponse({'success': True, 'message': f'Withdrawal request for ₦{amount} submitted successfully!'})


def logout_view(request):
    logout(request)
    return redirect('login')


def admin_logout_view(request):
    """Separate logout for the admin panel."""
    logout(request)
    return redirect('admin_login')


def index_view(request):
    return render(request, 'subcard_app/index.html')


def calculate_referral_bonuses(transaction):
    """
    Distribute referral bonuses when a transaction is made:
    - Level 1 (Direct): Uses plan-specific % (fallback to 15%)
    - Level 2 (Indirect): User's referrer's referrer gets 5%
    """
    user = transaction.user
    amount = transaction.amount

    # Default percentages
    level1_pct = Decimal('15.00')
    level2_pct = Decimal('5.00')

    # Try to get custom percentage from the plan if it's a data transaction
    if transaction.service == 'data' and transaction.plan_id:
        try:
            plan = Data_price.objects.filter(id=transaction.plan_id).first()
            if not plan:
                net_name = 'MTN' if transaction.network_id == 1 else ('Airtel' if transaction.network_id == 2 else ('GLO' if transaction.network_id == 4 else '9mobile'))
                network_obj = Network.objects.filter(name__iexact=net_name).first()
                if network_obj:
                    plan = Data_price.objects.filter(network=network_obj, networkid=transaction.plan_id).first()
                if not plan:
                    plan = Data_price.objects.filter(networkid=transaction.plan_id).first()

            if plan and plan.referral_percentage > 0:
                level1_pct = plan.referral_percentage
        except Exception:
            pass

    # Level 1: Direct referrer
    if user.referred_by:
        level1_bonus = amount * (level1_pct / 100)
        ReferralBonus.objects.create(
            beneficiary=user.referred_by,
            source_user=user,
            transaction=transaction,
            level=1,
            percentage=level1_pct,
            amount=level1_bonus
        )
        # Credit referrer's referral_wallet
        user.referred_by.referral_wallet += level1_bonus
        user.referred_by.save()

        # Level 2: Indirect referrer (referrer's referrer) gets 5%
        if user.referred_by.referred_by:
            level2_bonus = amount * (level2_pct / 100)
            ReferralBonus.objects.create(
                beneficiary=user.referred_by.referred_by,
                source_user=user,
                transaction=transaction,
                level=2,
                percentage=level2_pct,
                amount=level2_bonus
            )
            # Credit indirect referrer's referral_wallet
            user.referred_by.referred_by.referral_wallet += level2_bonus
            user.referred_by.referred_by.save()


@login_required
def dashboard_view(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    data, _ = CollectedData.objects.get_or_create(user=request.user)
    
    # Check for new transaction receipt
    new_transaction_id = request.session.pop('new_transaction_id', None)
    new_transaction = None
    if new_transaction_id:
        try:
            new_transaction = Transaction.objects.get(id=new_transaction_id, user=request.user)
        except Transaction.DoesNotExist:
            pass

    if request.method == 'POST':
        data.full_name = request.POST.get('full_name')
        data.address = request.POST.get('address')
        data.city = request.POST.get('city')
        data.state = request.POST.get('state')
        data.country = request.POST.get('country')
        data.save()
        messages.success(request, 'Data saved successfully.')
        return redirect('dashboard')

    referred_users = request.user.referrals.all()
    referral_count = referred_users.count()

    # Calculate referral earnings
    total_referral_earnings = sum(
        b.amount for b in request.user.referral_earnings.all()
    )
    level1_earnings = sum(
        b.amount for b in request.user.referral_earnings.filter(level=1)
    )
    level2_earnings = sum(
        b.amount for b in request.user.referral_earnings.filter(level=2)
    )

    # Recent transactions for display
    recent_transactions = request.user.transactions.order_by('-created_at')[:10]
    all_transactions = request.user.transactions.order_by('-created_at')
    MTN_network=Network.objects.get(name="MTN")
    airtel_network=Network.objects.get(name="Airtel")
    glo_network=Network.objects.get(name="GLO")
    nine_mobilenetwork=Network.objects.get(name="9mobile")
    settings = SiteSetting.load()
    
    active_dynamic = request.user.dynamic_accounts.filter(status='active', expiry_at__gt=timezone.now()).first()
    
    va_error = None
    # Auto-generate static virtual account if missing
    if settings.enable_static_va and not profile.has_virtual_account():
        full_name = request.user.get_full_name() or data.full_name or request.user.username
        if " " not in full_name:
            full_name = f"{full_name} User" # Fallback to avoid API error if single name
        phone = profile.phone or "08000000000"
        try:
            va_resp = create_static_virtual_account(
                email=request.user.email,
                name=full_name,
                phone=phone
            )
            print(f"DEBUG: Katpay Dashboard Auto-Create Response: {va_resp}")
            va_data = va_resp.get('data', {})
            if not va_data:
                # Some versions of the API might return the account details directly in the root
                va_data = va_resp
            
            profile.katpay_customer_id = va_data.get('uuid', '')
            profile.virtual_account_number = va_data.get('account_number', '') or va_data.get('accountNumber', '')
            profile.virtual_account_bank = va_data.get('bank_name', '') or va_data.get('bankName', '')
            profile.virtual_account_reference = va_data.get('reference', '')
            profile.virtual_account_status = 'active'
            profile.save()
            print(f"DEBUG: Saved Virtual Account for {request.user.username}: {profile.virtual_account_number}")
        except KatpayAPIError as e:
            va_error = str(e).replace("Virtual account creation failed: ", "")
            print(f"DEBUG: Katpay Dashboard Auto-Create Failed: {e}")

    def _plans(qs):
        return [{'id': p.networkid if p.networkid else p.id, 'networkid': p.networkid, 'name': f"{p.size} · {p.Duration}", 'price': p.price} for p in qs]

    data_plans_json = json.dumps({
        'mtn': _plans(Data_price.objects.filter(network=MTN_network)),
        'airtel': _plans(Data_price.objects.filter(network=airtel_network)),
        'glo': _plans(Data_price.objects.filter(network=glo_network)),
        '9mobile': _plans(Data_price.objects.filter(network=nine_mobilenetwork)),
    })

    # Recent cable transactions
    cable_transactions = request.user.transactions.filter(service='cable').order_by('-created_at')[:5]

    # Calculate statistics for activity cards (Monthly)
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # Airtime stats
    airtime_txns = request.user.transactions.filter(service='airtime', status='success', created_at__gte=month_start)
    airtime_spending = airtime_txns.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    airtime_count = airtime_txns.count()
    
    # Data stats
    data_txns = request.user.transactions.filter(service='data', status='success', created_at__gte=month_start)
    data_spending = data_txns.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    data_count = data_txns.count()
    
    # Cable stats
    cable_txns = request.user.transactions.filter(service='cable', status='success', created_at__gte=month_start)
    cable_spending = cable_txns.aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    cable_count = cable_txns.count()

    # Most used network
    from django.db.models import Count
    most_used_network_data = request.user.transactions.filter(status='success').values('network_id').annotate(count=Count('id')).order_by('-count').first()
    if most_used_network_data:
        net_id = most_used_network_data['network_id']
        net_name = "MTN" if net_id == 1 else "Airtel" if net_id == 2 else "Glo" if net_id == 4 else "9mobile" if net_id == 3 else "Unknown"
        most_used_network = {'name': net_name, 'count': most_used_network_data['count']}
    else:
        most_used_network = {'name': 'N/A', 'count': 0}

    # Last top-up (wallet funding)
    last_topup_txn = request.user.transactions.filter(service='wallet_funding', status='success').order_by('-created_at').first()
    if last_topup_txn:
        from django.utils.timesince import timesince
        last_topup = {
            'amount': last_topup_txn.amount,
            'time_str': f"{timesince(last_topup_txn.created_at).split(',')[0]} ago"
        }
    else:
        last_topup = None

    # Total transactions count for "Most used" display
    total_success_txns = request.user.transactions.filter(status='success').count()

    return render(request, 'subcard_app/dashboard.html', {
        'profile': profile,
        'data': data,
        'referral_code': request.user.referral_code,
        'referral_count': referral_count,
        'referral_wallet': request.user.referral_wallet,
        'referred_users': referred_users,
        'wallet_balance': request.user.wallet,
        'total_referral_earnings': total_referral_earnings,
        'level1_earnings': level1_earnings,
        'level2_earnings': level2_earnings,
        'all_transactions': all_transactions,
        'recent_transactions': recent_transactions,
        'most_used_network': most_used_network,
        'last_topup': last_topup,
        'total_success_txns': total_success_txns,
        'airtime_target': 5000,
        'data_target': 10000,
        'cable_target': 15000,
        'airtime_pct': min(int((airtime_spending / 5000) * 100), 100),
        'data_pct': min(int((data_spending / 10000) * 100), 100),
        'cable_pct': min(int((cable_spending / 15000) * 100), 100),
        'airtime_rem': max(5000 - airtime_spending, 0),
        'data_rem': max(10000 - data_spending, 0),
        'cable_rem': max(15000 - cable_spending, 0),
        'cable_transactions': cable_transactions,
        'cable_total_count': request.user.transactions.filter(service='cable').count(),
        'data_plans_json': data_plans_json,
        'stats': {
            'airtime': {'spending': airtime_spending, 'count': airtime_count},
            'data': {'spending': data_spending, 'count': data_count},
            'cable': {'spending': cable_spending, 'count': cable_count},
        },
        'virtual_account': {
            'has_account': profile.has_virtual_account(),
            'account_number': profile.virtual_account_number,
            'bank_name': profile.virtual_account_bank,
            'status': profile.virtual_account_status,
            'bvn': profile.bvn,
            'nin': profile.nin,
            'error': va_error,
        },
        'active_dynamic': active_dynamic,
        'enable_static_va': settings.enable_static_va,
        'enable_dynamic_va': settings.enable_dynamic_va,
        'new_transaction': new_transaction,
    })


@login_required
@require_POST
def update_profile(request):
    """Update user and profile information."""
    user = request.user
    profile, _ = Profile.objects.get_or_create(user=user)
    data, _ = CollectedData.objects.get_or_create(user=user)

    user.first_name = request.POST.get('first_name', user.first_name)
    user.last_name = request.POST.get('last_name', user.last_name)
    user.email = request.POST.get('email', user.email)
    user.save()

    profile.phone = request.POST.get('phone', profile.phone)
    profile.save()

    data.address = request.POST.get('address', data.address)
    data.state = request.POST.get('state', data.state)
    data.city = request.POST.get('city', data.city)
    data.save()

    messages.success(request, 'Profile updated successfully.')
    return redirect('dashboard')


@login_required
@require_POST
def update_password(request):
    """Securely change user password."""
    user = request.user
    current_password = request.POST.get('current_password')
    new_password = request.POST.get('new_password')
    confirm_password = request.POST.get('confirm_password')

    if not user.check_password(current_password):
        messages.error(request, 'Incorrect current password.')
        return redirect('dashboard')

    if new_password != confirm_password:
        messages.error(request, 'New passwords do not match.')
        return redirect('dashboard')

    if len(new_password) < 8:
        messages.error(request, 'Password must be at least 8 characters.')
        return redirect('dashboard')

    user.set_password(new_password)
    user.save()
    login(request, user)  # Keep the user logged in
    messages.success(request, 'Password updated successfully.')
    return redirect('dashboard')





@login_required
@require_POST
def create_virtual_account(request):
    """Create a Katpay static virtual account for the logged-in user."""
    profile = request.user.profile

    bvn = request.POST.get('bvn', '').strip()
    nin = request.POST.get('nin', '').strip()

    if not bvn and not nin:
        messages.error(request, 'Please provide either BVN or NIN.')
        return redirect('dashboard')

    # Use BVN if available, otherwise NIN
    verification_number = bvn if bvn else nin

    # Split full name into first and last
    full_name = request.user.get_full_name() or request.user.username
    phone = profile.phone or "08000000000"

    try:
        # Step 1: Create static virtual account
        va_resp = create_static_virtual_account(
            email=request.user.email,
            name=full_name,
            phone=phone
        )

        va_data = va_resp.get('data', {})
        # Depending on exact Katpay response. Docs aren't 100% clear for creation,
        # but the webhook returns account_number and bank_name.
        profile.katpay_customer_id = va_data.get('uuid', '')
        profile.virtual_account_number = va_data.get('account_number', '') or va_data.get('accountNumber', '')
        profile.virtual_account_bank = va_data.get('bank_name', '') or va_data.get('bankName', '')
        profile.virtual_account_reference = va_data.get('reference', '')
        profile.virtual_account_status = 'active'
        profile.bvn = bvn
        profile.nin = nin
        profile.save()

        messages.success(request, f"Virtual account created: {profile.virtual_account_bank} {profile.virtual_account_number}")
    except KatpayAPIError as e:
        messages.error(request, f'Virtual account creation failed: {e}')

    return redirect('dashboard')


@login_required
def data_plans_json(request):
    """Return data plans grouped by network for the frontend, supporting custom API providers."""
    provider_id = request.GET.get('provider_id')
    if provider_id:
        try:
            provider = get_object_or_404(APIProvider, id=provider_id)
            url = f"{provider.base_url.rstrip('/')}{provider.plans_endpoint}"
            headers = {
                provider.auth_header_key: provider.auth_header_value,
                'Accept': 'application/json',
            }
            if provider.additional_headers:
                try:
                    extra = json.loads(provider.additional_headers)
                    headers.update(extra)
                except Exception:
                    pass
            
            response = requests.get(url, headers=headers, timeout=30, verify=False)
            if response.status_code >= 200 and response.status_code < 300:
                res_json = response.json()
                
                # Unwrap if inside 'data' or 'plans'
                if isinstance(res_json, dict):
                    if 'data' in res_json:
                        res_json = res_json['data']
                    elif 'plans' in res_json:
                        res_json = res_json['plans']
                
                # Intelligent dynamic parser
                def fuzzy_group_plans(plans_list_or_dict):
                    grouped = {"1": [], "2": [], "3": [], "4": []}
                    if isinstance(plans_list_or_dict, dict):
                        has_numeric_keys = any(k in ["1", "2", "3", "4", 1, 2, 3, 4] for k in plans_list_or_dict.keys())
                        if has_numeric_keys:
                            for k, v in plans_list_or_dict.items():
                                str_k = str(k)
                                if str_k in grouped and isinstance(v, list):
                                    for p in v:
                                        grouped[str_k].append({
                                            "id": p.get("id") or p.get("plan_id") or p.get("networkid"),
                                            "name": p.get("name") or p.get("size") or p.get("plan_name") or "",
                                            "price": p.get("price") or p.get("telco_price") or p.get("amount") or 0
                                        })
                            return grouped
                        else:
                            for k, v in plans_list_or_dict.items():
                                if isinstance(v, list):
                                    return fuzzy_group_flat_list(v)
                    elif isinstance(plans_list_or_dict, list):
                        return fuzzy_group_flat_list(plans_list_or_dict)
                    return grouped

                def fuzzy_group_flat_list(flat_list):
                    grouped = {"1": [], "2": [], "3": [], "4": []}
                    for p in flat_list:
                        if not isinstance(p, dict):
                            continue
                        name = str(p.get("name") or p.get("size") or p.get("plan_name") or "").lower()
                        net_field = str(p.get("network") or p.get("network_name") or p.get("telco") or "").lower()
                        
                        net_id = "1"
                        if "airtel" in name or "airtel" in net_field or "2" == net_field:
                            net_id = "2"
                        elif "glo" in name or "glo" in net_field or "4" == net_field:
                            net_id = "4"
                        elif "9mobile" in name or "etisalat" in name or "9mobile" in net_field or "3" == net_field:
                            net_id = "3"
                        elif "mtn" in name or "mtn" in net_field or "1" == net_field:
                            net_id = "1"
                        
                        grouped[net_id].append({
                            "id": p.get("id") or p.get("plan_id") or p.get("networkid") or 0,
                            "name": p.get("name") or p.get("size") or p.get("plan_name") or "",
                            "price": p.get("price") or p.get("telco_price") or p.get("amount") or 0
                        })
                    return grouped

                parsed_plans = fuzzy_group_plans(res_json)
                return JsonResponse({'success': True, 'plans': parsed_plans})
            else:
                return JsonResponse({'success': False, 'error': f"API Error ({response.status_code}): {response.text[:200]}"})
        except Exception as e:
            return JsonResponse({'success': False, 'error': f"Failed to fetch custom plans: {str(e)}"})

    try:
        plans = get_data_plans()
        return JsonResponse({'success': True, 'plans': plans.get('data', {})})
    except SMEPlugAPIError as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=502)
def call_custom_api(provider, endpoint, payload):
    """Call dynamic custom API provider and return standard SMEPlug-like response."""
    url = f"{provider.base_url.rstrip('/')}{endpoint}"
    headers = {
        provider.auth_header_key: provider.auth_header_value,
        'Content-Type': 'application/json',
        'Accept': 'application/json',
    }
    if provider.additional_headers:
        try:
            extra = json.loads(provider.additional_headers)
            headers.update(extra)
        except Exception:
            pass
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60, verify=False)
        if response.status_code >= 200 and response.status_code < 300:
            res_json = {}
            try:
                res_json = response.json()
            except Exception:
                res_json = {"msg": response.text}
            
            status = True
            if 'status' in res_json:
                status = bool(res_json['status'])
            
            ref = res_json.get('reference', res_json.get('ref', res_json.get('data', {}).get('reference', '')))
            msg = res_json.get('msg', res_json.get('message', res_json.get('data', {}).get('msg', 'Transaction successful')))
            
            return {
                "status": status,
                "data": {
                    "reference": ref,
                    "msg": msg
                }
            }
        else:
            raise SMEPlugAPIError(f"API Error ({response.status_code}): {response.text[:200]}")
    except Exception as e:
        raise SMEPlugAPIError(f"API Connection Error: {str(e)}")



@login_required
@require_POST
def purchase_data_view(request):
    """Purchase a data bundle via SME Plug API."""
    network_name = request.POST.get('network', '')
    plan_id = request.POST.get('plan_id', '')
    phone = request.POST.get('phone', '')

    # PIN Validation
    pin_error = validate_transaction_pin(request)
    if pin_error:
        return pin_error


    # Handle both numeric IDs (from new form) and string names (legacy)
    try:
        network_id = int(network_name)
    except (ValueError, TypeError):
        network_id = NETWORK_MAP.get(network_name)
    if not network_id:
        messages.error(request, 'Invalid network selected.')
        return redirect('dashboard')

    # Fetch plan price from local database
    try:
        # Try finding by primary key ID first
        data_plan = Data_price.objects.filter(id=plan_id).first()
        if not data_plan:
            # Fallback: Query by network name and networkid to be completely precise
            net_name = 'MTN' if network_id == 1 else ('Airtel' if network_id == 2 else ('GLO' if network_id == 4 else '9mobile'))
            network_obj = Network.objects.filter(name__iexact=net_name).first()
            if network_obj:
                data_plan = Data_price.objects.filter(network=network_obj, networkid=plan_id).first()
            if not data_plan:
                data_plan = Data_price.objects.filter(networkid=plan_id).first()

        if not data_plan:
            raise Data_price.DoesNotExist

        price = Decimal(str(data_plan.price))
        description = f"{data_plan.size} · {data_plan.Duration}"
    except (Data_price.DoesNotExist, ValueError, TypeError):
        messages.error(request, 'Selected data plan not found.')
        return redirect('dashboard')

    # Check wallet balance
    if request.user.wallet < price:
        messages.error(request, f'Insufficient wallet balance. Required: ₦{price}')
        return redirect('dashboard')

    # Deduct from wallet
    request.user.wallet -= price
    request.user.save()

    customer_ref = generate_reference()
    transaction = Transaction.objects.create(
        user=request.user,
        service='data',
        amount=price,
        description=description,
        status='pending',
        network_id=network_id,
        phone=phone,
        plan_id=plan_id,
        customer_reference=customer_ref,
    )

    # Fetch Network and check custom API routing
    net_name = 'MTN' if network_id == 1 else ('Airtel' if network_id == 2 else ('GLO' if network_id == 4 else '9mobile'))
    network_obj = Network.objects.filter(name__iexact=net_name).first()

    try:
        if network_obj and network_obj.data_api:
            payload = {
                "network_id": network_id,
                "plan_id": plan_id,
                "phone": phone,
                "customer_reference": customer_ref
            }
            api_response = call_custom_api(network_obj.data_api, "/data/purchase", payload)
        else:
            api_response = purchase_data(network_id, plan_id, phone, customer_reference=customer_ref)
        transaction.api_response = json.dumps(api_response)
        transaction.reference = api_response.get('data', {}).get('reference', '')
        if api_response.get('status') is True:
            transaction.status = 'success'
            messages.success(
                request,
                api_response.get('data', {}).get('msg', 'Data purchased successfully!')
            )
            calculate_referral_bonuses(transaction)
            request.session['new_transaction_id'] = transaction.id
        else:
            transaction.status = 'failed'
            messages.error(request, 'Data purchase failed. Wallet has been refunded.')
            # Refund wallet
            request.user.wallet += price
            request.user.save()
    except SMEPlugAPIError as e:
        transaction.status = 'failed'
        transaction.api_response = str(e)
        messages.error(request, f'Data purchase failed: network connectivity failed. Wallet refunded.')
        # Refund wallet
        request.user.wallet += price
        request.user.save()
    finally:
        transaction.save()

    return redirect('dashboard')


@login_required
@require_POST
def purchase_airtime_view(request):
    """Purchase airtime via SME Plug API."""
    network_name = request.POST.get('network', '').strip()
    phone = request.POST.get('phone', '').strip()
    amount_str = request.POST.get('amount', '').strip()

    if not network_name or not phone or not amount_str:
        messages.error(request, 'Network, phone number and amount are required.')
        return redirect('dashboard')

    # PIN Validation
    pin_error = validate_transaction_pin(request)
    if pin_error:
        return pin_error



    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, 'Invalid amount entered.')
        return redirect('dashboard')

    # Handle both numeric IDs (from new form) and string names (legacy)
    try:
        network_id = int(network_name)
    except (ValueError, TypeError):
        network_id = NETWORK_MAP.get(network_name.lower())
    if not network_id:
        messages.error(request, 'Invalid network selected.')
        return redirect('dashboard')

    # Check wallet balance
    if request.user.wallet < amount:
        messages.error(request, f'Insufficient wallet balance. Required: ₦{amount}')
        return redirect('dashboard')

    # Deduct from wallet
    request.user.wallet -= amount
    request.user.save()

    customer_ref = generate_reference()
    transaction = Transaction.objects.create(
        user=request.user,
        service='airtime',
        amount=amount,
        description=f'Airtime ₦{amount} to {phone}',
        status='pending',
        network_id=network_id,
        phone=phone,
        customer_reference=customer_ref,
    )

    # Fetch Network and check custom API routing
    net_name = 'MTN' if network_id == 1 else ('Airtel' if network_id == 2 else ('GLO' if network_id == 4 else '9mobile'))
    network_obj = Network.objects.filter(name__iexact=net_name).first()

    try:
        if network_obj and network_obj.airtime_api:
            payload = {
                "network_id": network_id,
                "phone": phone,
                "amount": float(amount),
                "customer_reference": customer_ref
            }
            api_response = call_custom_api(network_obj.airtime_api, "/airtime/purchase", payload)
        else:
            api_response = purchase_airtime(network_id, phone, float(amount), customer_reference=customer_ref)
        transaction.api_response = json.dumps(api_response)
        transaction.reference = api_response.get('data', {}).get('reference', '')
        if api_response.get('status') is True:
            transaction.status = 'success'
            messages.success(
                request,
                api_response.get('data', {}).get('msg', 'Airtime purchased successfully!')
            )
            calculate_referral_bonuses(transaction)
            request.session['new_transaction_id'] = transaction.id
        else:
            transaction.status = 'failed'
            messages.error(request, 'Airtime purchase failed. Wallet has been refunded.')
            request.user.wallet += amount
            request.user.save()
    except SMEPlugAPIError as e:
        transaction.status = 'failed'
        transaction.api_response = str(e)
        messages.error(request, f'Airtime purchase failed: network conectivity. Wallet refunded.')
        request.user.wallet += amount
        request.user.save()
    finally:
        transaction.save()
    return redirect('dashboard')


# ─── Admin API Actions ────────────────────────────────────────────

def _admin_required(request):
    """Return JsonResponse error if request.user is not staff."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Admin access required.'}, status=403)
    return None


@login_required
@require_POST
def admin_update_user(request):
    err = _admin_required(request)
    if err: return err
    user_id = request.POST.get('user_id')
    email = request.POST.get('email')
    phone = request.POST.get('phone')
    is_active = request.POST.get('is_active')
    is_staff = request.POST.get('is_staff')
    is_email_verified = request.POST.get('is_email_verified')
    wallet = request.POST.get('wallet')
    try:
        user = CustomUser.objects.get(id=user_id)
        if email: user.email = email
        if phone: user.phone = phone
        if is_active is not None: user.is_active = is_active == 'true'
        if is_email_verified is not None: user.is_email_verified = is_email_verified == 'true'
        if is_staff is not None and request.user.is_superuser: user.is_staff = is_staff == 'true'
        if wallet: user.wallet = Decimal(wallet)
        user.save()
        try:
            p = user.profile
            if phone: p.phone = phone
            p.save()
        except Exception: pass
        return JsonResponse({'success': True, 'message': 'User updated.'})
    except CustomUser.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def admin_add_user(request):
    err = _admin_required(request)
    if err: return err
    username = request.POST.get('username', '').strip()
    email = request.POST.get('email', '').strip()
    phone = request.POST.get('phone', '').strip()
    password = request.POST.get('password', '').strip()
    is_staff = request.POST.get('is_staff', 'false') == 'true'
    if not username or not password:
        return JsonResponse({'success': False, 'error': 'Username and password required.'}, status=400)
    if CustomUser.objects.filter(username=username).exists():
        return JsonResponse({'success': False, 'error': 'Username already exists.'}, status=400)
    try:
        user = CustomUser.objects.create_user(username=username, email=email, password=password)
        user.phone = phone
        user.is_staff = is_staff
        user.save()
        Profile.objects.get_or_create(user=user, defaults={'phone': phone})
        return JsonResponse({'success': True, 'message': f'User "{username}" created.', 'id': user.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def admin_delete_user(request):
    err = _admin_required(request)
    if err: return err
    user_id = request.POST.get('user_id')
    try:
        user = CustomUser.objects.get(id=user_id)
        if user == request.user:
            return JsonResponse({'success': False, 'error': 'Cannot delete yourself.'}, status=400)
        uname = user.username
        user.delete()
        return JsonResponse({'success': True, 'message': f'User "{uname}" deleted.'})
    except CustomUser.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def admin_fund_wallet(request):
    err = _admin_required(request)
    if err: return err
    user_id = request.POST.get('user_id')
    amount_str = request.POST.get('amount', '0')
    action = request.POST.get('action', 'credit')
    try:
        user = CustomUser.objects.get(id=user_id)
        amount = Decimal(amount_str)
        if action == 'debit':
            user.wallet = max(Decimal('0'), user.wallet - amount)
        else:
            user.wallet += amount
        user.save()
        return JsonResponse({'success': True, 'message': f'Wallet updated. Balance: \u20a6{user.wallet:,.2f}'})
    except CustomUser.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def admin_transaction_receipt(request, transaction_id):
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Admin access required.'}, status=403)
    try:
        txn = Transaction.objects.select_related('user').get(id=transaction_id)
        return JsonResponse({'success': True, 'receipt': {
            'transaction_id': txn.id, 'reference': txn.reference,
            'customer_reference': txn.customer_reference,
            'user': {'id': txn.user.id, 'username': txn.user.username, 'email': txn.user.email},
            'service': txn.service, 'amount': str(txn.amount), 'description': txn.description,
            'status': txn.status, 'phone': txn.phone, 'plan_id': txn.plan_id,
            'network_id': txn.network_id, 'created_at': txn.created_at.isoformat(),
            'api_response': txn.api_response or None,
        }})
    except Transaction.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Transaction not found.'}, status=404)


@login_required
@require_POST
def admin_delete_transaction(request):
    err = _admin_required(request)
    if err: return err
    txn_id = request.POST.get('transaction_id')
    try:
        t = Transaction.objects.get(id=txn_id)
        t.delete()
        return JsonResponse({'success': True, 'message': 'Transaction deleted.'})
    except Transaction.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def admin_update_data_price(request):
    err = _admin_required(request)
    if err: return err
    plan_id = request.POST.get('plan_id')
    price = request.POST.get('price')
    size = request.POST.get('size')
    duration = request.POST.get('duration')
    networkid = request.POST.get('networkid')
    try:
        plan = Data_price.objects.get(id=plan_id)
        if price: plan.price = int(price)
        if size: plan.size = size
        if duration: plan.Duration = duration
        if networkid: plan.networkid = int(networkid)
        if request.POST.get('referral_percentage'):
            plan.referral_percentage = Decimal(request.POST.get('referral_percentage'))
        plan.save()
        return JsonResponse({'success': True, 'message': 'Plan updated.'})
    except Data_price.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Plan not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def admin_add_data_price(request):
    err = _admin_required(request)
    if err: return err
    network_name = request.POST.get('network', '').strip()
    size = request.POST.get('size', '').strip()
    price = request.POST.get('price', '0').strip()
    duration = request.POST.get('duration', '').strip()
    networkid = request.POST.get('networkid', '0').strip()
    try:
        network = Network.objects.get(name__iexact=network_name)
        ref_pct = request.POST.get('referral_percentage', '0')
        plan = Data_price.objects.create(
            network=network, 
            size=size, 
            price=int(price), 
            Duration=duration, 
            networkid=int(networkid),
            referral_percentage=Decimal(ref_pct)
        )
        return JsonResponse({'success': True, 'message': 'Plan added.', 'id': plan.id})
    except Network.DoesNotExist:
        return JsonResponse({'success': False, 'error': f'Network "{network_name}" not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def admin_delete_data_price(request):
    err = _admin_required(request)
    if err: return err
    plan_id = request.POST.get('plan_id')
    try:
        p = Data_price.objects.get(id=plan_id)
        p.delete()
        return JsonResponse({'success': True, 'message': 'Plan deleted.'})
    except Data_price.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def admin_update_referral(request):
    err = _admin_required(request)
    if err: return err
    referral_id = request.POST.get('referral_id')
    percentage = request.POST.get('percentage')
    amount = request.POST.get('amount')
    try:
        r = ReferralBonus.objects.get(id=referral_id)
        if percentage: r.percentage = Decimal(percentage)
        if amount: r.amount = Decimal(amount)
        r.save()
        return JsonResponse({'success': True, 'message': 'Referral updated.'})
    except ReferralBonus.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Referral not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_POST
def admin_delete_referral(request):
    err = _admin_required(request)
    if err: return err
    ref_id = request.POST.get('referral_id')
    try:
        r = ReferralBonus.objects.get(id=ref_id)
        r.delete()
        return JsonResponse({'success': True, 'message': 'Referral deleted.'})
    except ReferralBonus.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def smeplug_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'POST only'}, status=405)
    try:
        payload = json.loads(request.body)
        txn_data = payload.get('transaction', {})
        status = txn_data.get('status', '')
        reference = txn_data.get('reference', '')
        customer_ref = txn_data.get('customer_reference', '')
        transaction = None
        if customer_ref:
            transaction = Transaction.objects.filter(customer_reference=customer_ref).first()
        if not transaction and reference:
            transaction = Transaction.objects.filter(reference=reference).first()
        if transaction:
            prev_status = transaction.status
            transaction.status = status
            transaction.api_response = json.dumps(payload)
            transaction.save()
            if status == 'failed' and prev_status != 'failed':
                transaction.user.wallet += transaction.amount
                transaction.user.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


def admin_view(request):
    """Full admin dashboard — staff only."""
    if not request.user.is_authenticated or not request.user.is_staff:
        messages.error(request, 'Admin login required.')
        return redirect('admin_login')

    User = get_user_model()
    all_users = User.objects.prefetch_related('transactions').all()
    all_txns = Transaction.objects.select_related('user').order_by('-created_at')[:500]

    total_users = all_users.count()
    active_users = all_users.filter(is_active=True).count()
    staff_users = all_users.filter(is_staff=True).count()
    superusers = all_users.filter(is_superuser=True).count()

    total_revenue = Transaction.objects.filter(status='success').aggregate(
        total=models.Sum('amount'))['total'] or 0
    total_wallets = CustomUser.objects.aggregate(total=models.Sum('wallet'))['total'] or 0
    successful_txns = Transaction.objects.filter(status='success').count()
    failed_txns = Transaction.objects.filter(status='failed').count()
    pending_txns = Transaction.objects.filter(status='pending').count()
    total_txns = Transaction.objects.count()

    service_totals = {}
    for svc, lbl in Transaction.SERVICE_CHOICES:
        amt = Transaction.objects.filter(status='success', service=svc).aggregate(
            total=models.Sum('amount'))['total'] or 0
        service_totals[svc] = float(amt)

    mtn = Network.objects.filter(name='MTN').first()
    airtel = Network.objects.filter(name='Airtel').first()
    glo = Network.objects.filter(name='GLO').first()
    nine = Network.objects.filter(name='9mobile').first()
    data_prices = {
        'mtn': Data_price.objects.filter(network=mtn) if mtn else [],
        'airtel': Data_price.objects.filter(network=airtel) if airtel else [],
        'glo': Data_price.objects.filter(network=glo) if glo else [],
        '9mobile': Data_price.objects.filter(network=nine) if nine else [],
    }
    va_count = Profile.objects.exclude(virtual_account_number='').count()
    all_networks = list(Network.objects.values('id', 'name'))
    settings = SiteSetting.load()

    NETWORK_NAMES = {1: 'MTN', 2: 'Airtel', 4: 'GLO', 3: '9mobile'}

    users_json = json.dumps([{
        'id': u.id, 'username': u.username,
        'name': u.get_full_name() or u.username,
        'email': u.email, 'phone': u.phone or '-',
        'wallet': float(u.wallet), 'wallet_display': f'\u20a6{u.wallet:,.0f}',
        'txns': u.transactions.count(),
        'is_active': u.is_active, 'is_staff': u.is_staff, 'is_superuser': u.is_superuser,
        'is_email_verified': u.is_email_verified,
        'status': 'active' if u.is_active else 'suspended',
        'joined': u.date_joined.strftime('%b %d, %Y'),
        'referral_code': u.referral_code,
    } for u in all_users])

    txns_json = json.dumps([{
        'id': t.id, 'ref': t.customer_reference or f'TXN{t.id:04d}',
        'user': t.user.username, 'user_id': t.user.id,
        'type': t.service, 'amount': float(t.amount),
        'amount_display': f'\u20a6{t.amount:,.0f}',
        'network': NETWORK_NAMES.get(t.network_id, t.service.upper()),
        'phone': t.phone, 'description': t.description,
        'status': t.status, 'date': t.created_at.strftime('%b %d, %H:%M'),
    } for t in all_txns])

    total_svc = sum(service_totals.values()) or 1
    svc_breakdown = {k: round((v / total_svc) * 100, 1) for k, v in service_totals.items()}

    all_plans = []
    for net, plans in data_prices.items():
        for plan in plans:
            all_plans.append({'id': plan.id, 'network': net, 'size': plan.size,
                              'price': plan.price, 'duration': plan.Duration, 'networkid': plan.networkid,
                              'referral_percentage': str(plan.referral_percentage)})
    data_prices_json = json.dumps(all_plans)

    referrals = ReferralBonus.objects.select_related('beneficiary', 'source_user').order_by('-created_at')[:200]
    referrals_json = json.dumps([{
        'id': r.id, 'beneficiary': r.beneficiary.username,
        'beneficiary_id': r.beneficiary.id,
        'source_user': r.source_user.username,
        'level': r.level, 'percentage': str(r.percentage),
        'amount': float(r.amount), 'amount_display': f'\u20a6{r.amount:,.2f}',
        'transaction_id': r.transaction.id if r.transaction else None,
        'created_at': r.created_at.strftime('%b %d, %Y'),
    } for r in referrals])

    initials = ((request.user.first_name[:1] + request.user.last_name[:1]).upper()
                or request.user.username[:2].upper())

    from django.utils.timesince import timesince
    from django.utils.timezone import now
    from datetime import timedelta
    from django.db.models import Sum
    
    current_time = now()
    
    # 7-day revenue chart
    today = current_time.date()
    chart_data = []
    days_labels = []
    max_rev = 0
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        rev = Transaction.objects.filter(status='success', created_at__date=d).aggregate(Sum('amount'))['amount__sum'] or 0
        rev = float(rev)
        chart_data.append(rev)
        days_labels.append(d.strftime('%a'))
        if rev > max_rev: max_rev = rev
            
    chart_json = json.dumps({'data': chart_data, 'labels': days_labels, 'max': max_rev or 1})
    
    # Donut chart geometry
    circ = 188.5
    a_pct, d_pct, c_pct = svc_breakdown.get('airtime', 0), svc_breakdown.get('data', 0), svc_breakdown.get('cable', 0)
    a_dash = (a_pct / 100.0) * circ
    d_dash = (d_pct / 100.0) * circ
    c_dash = (c_pct / 100.0) * circ
    donut_data = {
        'a_dash': f"{a_dash:.1f} {circ}",
        'd_dash': f"{d_dash:.1f} {circ}",
        'c_dash': f"{c_dash:.1f} {circ}",
        'a_off': 0, 'd_off': f"-{a_dash:.1f}", 'c_off': f"-{(a_dash+d_dash):.1f}"
    }

    recent_activity = []
    
    for u in CustomUser.objects.order_by('-date_joined')[:20]:
        hours_ago = (current_time - u.date_joined).total_seconds() / 3600
        recent_activity.append({
            'type': 'user', 'icon': 'user', 'color': 'green',
            'text': f"New user registered — {u.username}",
            'date': u.date_joined, 'time_str': f"{timesince(u.date_joined).split(',')[0]} ago",
            'hours_ago': hours_ago
        })
        
    for t in Transaction.objects.order_by('-created_at')[:80]:
        hours_ago = (current_time - t.created_at).total_seconds() / 3600
        if t.status == 'failed':
            text = f"Failed txn — {t.customer_reference or t.reference}"
            icon, color = 'alert', 'red'
        elif t.status == 'success' and t.amount >= 5000:
            text = f"Large txn ₦{t.amount:,.0f} — {t.user.username}"
            icon, color = 'star', 'blue'
        elif t.status == 'success':
            text = f"Txn ₦{t.amount:,.0f} — {t.user.username}"
            icon, color = 'check', 'green'
        else:
            text = f"Pending txn ₦{t.amount:,.0f} — {t.user.username}"
            icon, color = 'clock', 'amber'
        recent_activity.append({
            'type': 'txn', 'icon': icon, 'color': color,
            'text': text, 'date': t.created_at,
            'time_str': f"{timesince(t.created_at).split(',')[0]} ago",
            'hours_ago': hours_ago
        })
        
    recent_activity.sort(key=lambda x: x['date'], reverse=True)
    for act in recent_activity:
        act.pop('date')
        
    # Stats comparison
    this_month_start = today.replace(day=1)
    # Approx last month start/end
    last_month_end = this_month_start - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)
    
    def get_pct(svc):
        curr = Transaction.objects.filter(service=svc, status='success', created_at__date__gte=this_month_start).aggregate(Sum('amount'))['amount__sum'] or 0
        prev = Transaction.objects.filter(service=svc, status='success', created_at__date__gte=last_month_start, created_at__date__lte=last_month_end).aggregate(Sum('amount'))['amount__sum'] or 0
        if prev: return round((float(curr) - float(prev)) / float(prev) * 100)
        return 100 if curr else 0
        
    airtime_pct = get_pct('airtime')
    data_pct = get_pct('data')
    cable_pct = get_pct('cable')
    
    yesterday = today - timedelta(days=1)
    failed_today = Transaction.objects.filter(status='failed', created_at__date=today).count()
    failed_yesterday = Transaction.objects.filter(status='failed', created_at__date=yesterday).count()
    failed_diff = failed_today - failed_yesterday
    
    airtime_pct_str = f"▲ {airtime_pct}% vs last month" if airtime_pct >= 0 else f"▼ {abs(airtime_pct)}% vs last month"
    airtime_pct_cls = "up" if airtime_pct >= 0 else "down"
    data_pct_str = f"▲ {data_pct}% vs last month" if data_pct >= 0 else f"▼ {abs(data_pct)}% vs last month"
    data_pct_cls = "up" if data_pct >= 0 else "down"
    cable_pct_str = f"▲ {cable_pct}% vs last month" if cable_pct >= 0 else f"▼ {abs(cable_pct)}% vs last month"
    cable_pct_cls = "up" if cable_pct >= 0 else "down"
    failed_str = f"▼ {abs(failed_diff)} less than yesterday" if failed_diff < 0 else (f"▲ {failed_diff} more than yesterday" if failed_diff > 0 else "Same as yesterday")
    failed_cls = "down" if failed_diff <= 0 else "up"
    
    # Today's transaction stats
    tot_today_amt = float(Transaction.objects.filter(status='success', created_at__date=today).aggregate(Sum('amount'))['amount__sum'] or 0)
    tot_yest_amt = float(Transaction.objects.filter(status='success', created_at__date=yesterday).aggregate(Sum('amount'))['amount__sum'] or 0)
    if tot_yest_amt > 0: tot_today_pct = round(((tot_today_amt - tot_yest_amt) / tot_yest_amt) * 100, 1)
    else: tot_today_pct = 100 if tot_today_amt > 0 else 0

    tot_today_str = f"▲ {tot_today_pct}% vs yesterday" if tot_today_pct >= 0 else f"▼ {abs(tot_today_pct)}% vs yesterday"
    tot_today_cls = "up" if tot_today_pct >= 0 else "down"

    success_today = Transaction.objects.filter(status='success', created_at__date=today).count()
    pending_today = Transaction.objects.filter(status='pending', created_at__date=today).count()
    
    total_txns_today = success_today + pending_today + failed_today
    if total_txns_today > 0:
        success_rate = round((success_today / total_txns_today) * 100, 1)
        fail_rate = round((failed_today / total_txns_today) * 100, 1)
    else:
        success_rate = 0
        fail_rate = 0
        
    # User stats
    week_ago = today - timedelta(days=7)
    users_this_week = CustomUser.objects.filter(date_joined__date__gte=week_ago).count()
    verified_pct = round((active_users / total_users * 100), 1) if total_users > 0 else 0
    suspended_users = total_users - active_users
    
    # Service targets
    a_tot = service_totals.get('airtime', 0)
    d_tot = service_totals.get('data', 0)
    c_tot = service_totals.get('cable', 0)
    a_target = max(a_tot * 1.5, 1000)
    d_target = max(d_tot * 1.5, 1000)
    c_target = max(c_tot * 1.5, 1000)
    a_bar = min(round((a_tot / a_target) * 100), 100) if a_target else 0
    d_bar = min(round((d_tot / d_target) * 100), 100) if d_target else 0
    c_bar = min(round((c_tot / c_target) * 100), 100) if c_target else 0
    
    # Reports Panel
    rep_month_name = today.strftime("%B %Y")
    # Revenue
    rep_rev_this = float(Transaction.objects.filter(status='success', created_at__date__gte=this_month_start).aggregate(Sum('amount'))['amount__sum'] or 0)
    rep_rev_last = float(Transaction.objects.filter(status='success', created_at__date__gte=last_month_start, created_at__date__lte=last_month_end).aggregate(Sum('amount'))['amount__sum'] or 0)
    if rep_rev_last > 0: rep_rev_pct = round(((rep_rev_this - rep_rev_last) / rep_rev_last) * 100, 1)
    else: rep_rev_pct = 100 if rep_rev_this > 0 else 0
    rep_rev_str = f"+{rep_rev_pct}%" if rep_rev_pct >= 0 else f"{rep_rev_pct}%"
    rep_rev_bar = min(round((rep_rev_this / max(rep_rev_last, 1)) * 50), 100) if rep_rev_this >= rep_rev_last else min(round((rep_rev_this / max(rep_rev_last, 1)) * 100), 100)
    if rep_rev_bar == 0 and rep_rev_this > 0: rep_rev_bar = 100

    # User Growth
    rep_users_this = CustomUser.objects.filter(date_joined__date__gte=this_month_start).count()
    rep_users_last = CustomUser.objects.filter(date_joined__date__gte=last_month_start, date_joined__date__lte=last_month_end).count()
    if rep_users_last > 0: rep_users_pct = round(((rep_users_this - rep_users_last) / rep_users_last) * 100, 1)
    else: rep_users_pct = 100 if rep_users_this > 0 else 0
    rep_users_str = f"+{rep_users_pct}%" if rep_users_pct >= 0 else f"{rep_users_pct}%"
    rep_users_bar = min(round((rep_users_this / max(rep_users_last, 1)) * 50), 100) if rep_users_this >= rep_users_last else min(round((rep_users_this / max(rep_users_last, 1)) * 100), 100)
    if rep_users_bar == 0 and rep_users_this > 0: rep_users_bar = 100
    
    # Success Rate
    sr_succ_this = Transaction.objects.filter(status='success', created_at__date__gte=this_month_start).count()
    sr_tot_this = Transaction.objects.filter(created_at__date__gte=this_month_start).count()
    rep_sr_this = round((sr_succ_this / sr_tot_this) * 100, 1) if sr_tot_this > 0 else 0
    
    sr_succ_last = Transaction.objects.filter(status='success', created_at__date__gte=last_month_start, created_at__date__lte=last_month_end).count()
    sr_tot_last = Transaction.objects.filter(created_at__date__gte=last_month_start, created_at__date__lte=last_month_end).count()
    rep_sr_last = round((sr_succ_last / sr_tot_last) * 100, 1) if sr_tot_last > 0 else 0
    
    rep_sr_diff = round(rep_sr_this - rep_sr_last, 1)
    rep_sr_str = f"+{rep_sr_diff}pp" if rep_sr_diff >= 0 else f"{rep_sr_diff}pp"

    context = {
        'admin_username': request.user.username,
        'admin_initials': initials,
        'recent_activity_json': json.dumps(recent_activity),
        'chart_json': chart_json,
        'donut_data': donut_data,
        'total_users': total_users, 'active_users': active_users,
        'staff_users': staff_users, 'superusers': superusers,
        'total_revenue': total_revenue, 'total_wallets': total_wallets,
        'successful_txns': successful_txns, 'failed_txns': failed_txns,
        'pending_txns': pending_txns, 'total_txns': total_txns,
        'service_totals': service_totals, 'svc_breakdown': svc_breakdown,
        'users_json': users_json, 'txns_json': txns_json,
        'data_prices_json': data_prices_json, 'referrals_json': referrals_json,
        'data_prices': data_prices, 'va_count': va_count,
        'all_networks': json.dumps(all_networks),
        # Backward-compat vars for existing template
        'totalUser': total_users,
        'active_user': active_users,
        'failed': failed_txns,
        'success': successful_txns,
        'success_today': successful_txns,
        'airtime_sale': f"{service_totals.get('airtime', 0):,.0f}",
        'data_sale': f"{service_totals.get('data', 0):,.0f}",
        'cable_sale': f"{service_totals.get('cable', 0):,.0f}",
        'airtime_pct_str': airtime_pct_str, 'airtime_pct_cls': airtime_pct_cls,
        'data_pct_str': data_pct_str, 'data_pct_cls': data_pct_cls,
        'cable_pct_str': cable_pct_str, 'cable_pct_cls': cable_pct_cls,
        'failed_str': failed_str, 'failed_cls': failed_cls,
        'tot_today_amt': f"{tot_today_amt:,.0f}", 'tot_today_str': tot_today_str, 'tot_today_cls': tot_today_cls,
        'success_today': success_today, 'success_rate': success_rate,
        'pending_today': pending_today, 'failed_today': failed_today, 'fail_rate': fail_rate,
        'users_this_week': users_this_week, 'verified_pct': verified_pct, 'suspended_users': suspended_users,
        'a_tot': f"{a_tot:,.0f}", 'a_target': f"{a_target:,.0f}", 'a_bar': a_bar,
        'd_tot': f"{d_tot:,.0f}", 'd_target': f"{d_target:,.0f}", 'd_bar': d_bar,
        'c_tot': f"{c_tot:,.0f}", 'c_target': f"{c_target:,.0f}", 'c_bar': c_bar,
        'rep_month_name': rep_month_name,
        'rep_rev_this': f"₦{rep_rev_this:,.0f}", 'rep_rev_last': f"₦{rep_rev_last:,.0f}", 'rep_rev_str': rep_rev_str, 'rep_rev_bar': rep_rev_bar,
        'rep_users_this': rep_users_this, 'rep_users_last': rep_users_last, 'rep_users_str': rep_users_str, 'rep_users_bar': rep_users_bar,
        'rep_sr_this': rep_sr_this, 'rep_sr_last': rep_sr_last, 'rep_sr_str': rep_sr_str,
        'airtime_pecentage': svc_breakdown.get('airtime', 0),
        'data_pecentage': svc_breakdown.get('data', 0),
        'cable_pecentage': svc_breakdown.get('cable', 0),
        'api_providers': APIProvider.objects.all().order_by('-created_at'),
        'networks': Network.objects.all().prefetch_related('data_api', 'airtime_api'),
        'withdrawals': Withdrawal.objects.select_related('user').order_by('-created_at')[:200],
    }
    return render(request, 'subcard_app/subcard_admin.html', context)


@login_required
@require_POST
def admin_handle_withdrawal(request, withdrawal_id):
    if not request.user.is_staff:
        messages.error(request, 'Unauthorized')
        return redirect('admin_panel')
        
    withdrawal = get_object_or_404(Withdrawal, id=withdrawal_id)
    action = request.POST.get('action')
    
    if action == 'approve':
        withdrawal.status = 'approved'
        withdrawal.save()
        messages.success(request, f'Withdrawal for {withdrawal.user.username} approved.')
    elif action == 'reject':
        withdrawal.status = 'rejected'
        withdrawal.save()
        # Refund referral wallet
        withdrawal.user.referral_wallet += withdrawal.amount
        withdrawal.user.save()
        messages.success(request, f'Withdrawal for {withdrawal.user.username} rejected. Amount refunded.')
        
    return redirect('admin_panel')


def mypannel(request):
    return redirect('admin_panel')


@login_required
@require_POST
def admin_save_api_provider(request):
    """Save (create or update) an API Provider."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
    
    provider_id = request.POST.get('provider_id')
    name = request.POST.get('name', '').strip()
    base_url = request.POST.get('base_url', '').strip()
    auth_header_key = request.POST.get('auth_header_key', 'Authorization').strip()
    auth_header_value = request.POST.get('auth_header_value', '').strip()
    additional_headers = request.POST.get('additional_headers', '{}').strip()

    if not name or not base_url or not auth_header_value:
        return JsonResponse({'success': False, 'error': 'Name, Base URL, and Auth Value are required.'})

    try:
        json.loads(additional_headers) # validate JSON
    except Exception:
        return JsonResponse({'success': False, 'error': 'Additional Headers must be in valid JSON format.'})

    plans_endpoint = request.POST.get('plans_endpoint', '/plans').strip() or '/plans'

    if provider_id:
        provider = get_object_or_404(APIProvider, id=provider_id)
        provider.name = name
        provider.base_url = base_url
        provider.auth_header_key = auth_header_key
        provider.auth_header_value = auth_header_value
        provider.additional_headers = additional_headers
        provider.plans_endpoint = plans_endpoint
        provider.save()
        messages.success(request, f"API Provider '{name}' updated successfully.")
    else:
        APIProvider.objects.create(
            name=name,
            base_url=base_url,
            auth_header_key=auth_header_key,
            auth_header_value=auth_header_value,
            additional_headers=additional_headers,
            plans_endpoint=plans_endpoint
        )
        messages.success(request, f"API Provider '{name}' created successfully.")

    return JsonResponse({'success': True})


@login_required
@require_POST
def admin_delete_api_provider(request):
    """Delete an API Provider. When deleted, everything referencing it cascades/updates."""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        
    provider_id = request.POST.get('provider_id')
    if not provider_id:
        return JsonResponse({'success': False, 'error': 'Provider ID is required.'})

    provider = get_object_or_404(APIProvider, id=provider_id)
    name = provider.name
    provider.delete()
    messages.success(request, f"API Provider '{name}' and all its references have been deleted.")
    return JsonResponse({'success': True})


@login_required
@require_POST
def admin_save_network_routing(request):
    """Update API Provider assignments for different networks."""
    if not request.user.is_staff:
        messages.error(request, 'Unauthorized action.')
        return redirect('admin_panel')
        
    for network in Network.objects.all():
        data_api_id = request.POST.get(f'data_api_{network.id}')
        airtime_api_id = request.POST.get(f'airtime_api_{network.id}')

        if data_api_id:
            network.data_api = APIProvider.objects.filter(id=data_api_id).first()
        else:
            network.data_api = None

        if airtime_api_id:
            network.airtime_api = APIProvider.objects.filter(id=airtime_api_id).first()
        else:
            network.airtime_api = None

        network.save()

    messages.success(request, "Network API routing updated successfully.")
    return redirect('admin_panel')


@login_required
@require_POST
def admin_send_broadcast(request):
    """Send bulk email to all users in the database."""
    err = _admin_required(request)
    if err: return err
    
    try:
        subject = request.POST.get('subject')
        message_html = request.POST.get('message')
        
        if not subject or not message_html:
            return JsonResponse({'success': False, 'error': 'Subject and message are required.'})
        
        # Get all users with email — or just one if single_email is set
        single_email = request.POST.get('single_email', '').strip()
        if single_email:
            users = User.objects.filter(email=single_email)
        else:
            users = User.objects.exclude(email='').exclude(email__isnull=True)
        count = 0
        
        site_url = request.build_absolute_uri('/')
        
        for user in users:
            try:
                # Prepare context for the template
                email_context = {
                    'username': user.username,
                    'subject': subject,
                    'message': message_html,
                    'site_url': site_url,
                }
                
                # Render the HTML template
                html_message = render_to_string('subcard_app/email_broadcast_template.html', email_context)
                plain_message = strip_tags(html_message)
                
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=django_settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    html_message=html_message,
                    fail_silently=True,
                )
                count += 1
            except:
                continue
        
        return JsonResponse({
            'success': True, 
            'message': f'Broadcast sent successfully to {count} users.'
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def admin_update_settings(request):
    err = _admin_required(request)
    if err: return err
    try:
        settings = SiteSetting.load()

        # Numeric / limit fields
        min_airtime = request.POST.get('min_airtime')
        max_airtime = request.POST.get('max_airtime')
        daily_wallet_limit = request.POST.get('daily_wallet_limit')
        if min_airtime: settings.min_airtime = Decimal(min_airtime)
        if max_airtime: settings.max_airtime = Decimal(max_airtime)
        if daily_wallet_limit: settings.daily_wallet_limit = Decimal(daily_wallet_limit)

        # Boolean toggle fields ('true' / 'false' strings from JS)
        def _bool(key):
            val = request.POST.get(key)
            if val is None:
                return None
            return val.lower() in ('true', '1', 'on', 'yes')

        m = _bool('maintenance_mode')
        if m is not None: settings.maintenance_mode = m

        e = _bool('email_notifications')
        if e is not None: settings.email_notifications = e

        s = _bool('sms_notifications')
        if s is not None: settings.sms_notifications = s

        k = _bool('auto_kyc')
        if k is not None: settings.auto_kyc = k

        f = _bool('fraud_detection')
        if f is not None: settings.fraud_detection = f

        settings.save()
        return JsonResponse({'success': True, 'message': 'Settings updated successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_POST
def admin_update_account(request):
    err = _admin_required(request)
    if err: return err
    admin_name = request.POST.get('admin_name')
    email = request.POST.get('email')
    password = request.POST.get('password')
    try:
        user = request.user
        if admin_name:
            user.first_name = admin_name
        if email:
            user.email = email
        if password:
            user.set_password(password)
        user.save()
        if password:
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)
        return JsonResponse({'success': True, 'message': 'Account updated successfully.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def admin_export_csv(request):
    err = _admin_required(request)
    if err: return err
    report_type = request.GET.get('type', 'users')
    response = HttpResponse(content_type='text/csv')
    if report_type == 'users':
        response['Content-Disposition'] = 'attachment; filename="users_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['ID', 'Username', 'Email', 'Phone', 'Wallet', 'Status', 'Joined'])
        users = CustomUser.objects.all()
        for u in users:
            writer.writerow([u.id, u.username, u.email, u.phone, u.wallet, 'Active' if u.is_active else 'Suspended', u.date_joined.strftime('%Y-%m-%d')])
    elif report_type == 'transactions':
        response['Content-Disposition'] = 'attachment; filename="transactions_report.csv"'
        writer = csv.writer(response)
        writer.writerow(['Ref', 'User', 'Service', 'Amount', 'Status', 'Date'])
        txns = Transaction.objects.all()
        for t in txns:
            writer.writerow([t.customer_reference or t.reference, t.user.username, t.service, t.amount, t.status, t.created_at.strftime('%Y-%m-%d %H:%M')])
    else:
        return HttpResponse('Invalid report type.', status=400)
    return response


@login_required
@require_POST
def request_dynamic_va(request):
    amount = request.POST.get('amount')
    if not amount:
        return JsonResponse({'success': False, 'error': 'Amount is required'})
    
    try:
        amount = Decimal(amount)
        if amount <= 0:
            return JsonResponse({'success': False, 'error': 'Invalid amount'})
        
        full_name = request.user.get_full_name() or request.user.username
        phone = request.user.profile.phone or "08000000000"
        reference = katpay_generate_reference()
        
        # Create dynamic VA via Katpay API
        va_resp = create_dynamic_virtual_account(
            amount=amount,
            customer_name=full_name,
            customer_email=request.user.email,
            customer_phone=phone,
            reference=reference,
            description=f"Funding for {request.user.username}"
        )
        
        # Save to DB
        va_data = va_resp.get('data', {})
        payment_account = va_data.get('payment_account', {})
        
        DynamicVirtualAccount.objects.create(
            user=request.user,
            amount=amount,
            reference=reference,
            account_number=payment_account.get('account_number'),
            bank_name=payment_account.get('bank_name'),
            expiry_at=timezone.now() + timedelta(seconds=60*60),
            status='active'
        )
        
        return JsonResponse({
            'success': True,
            'account_number': payment_account.get('account_number'),
            'bank_name': payment_account.get('bank_name'),
            'amount': float(amount)
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_POST
def katpay_webhook(request):
    payload = request.body.decode('utf-8')
    signature = request.headers.get('X-Katpay-Signature', '')
    timestamp = request.headers.get('X-Katpay-Timestamp', '')
    
    print(f"DEBUG: Katpay Webhook received. Signature: {signature}, Timestamp: {timestamp}")
    print(f"DEBUG: Payload: {payload}")
    
    secret_key = getattr(django_settings, 'KATPAY_SECRET_KEY', '')
    
    if not secret_key:
        print("DEBUG: Katpay Webhook - Secret not configured")
        return JsonResponse({'error': 'Webhook secret not configured'}, status=500)
        
    if not signature or not timestamp:
        print("DEBUG: Katpay Webhook - Missing headers")
        return JsonResponse({'error': 'Missing required headers'}, status=400)
    
    # 1. Verify signature
    signed_payload = f"{timestamp}.{payload}"
    expected_signature = hmac.new(
        secret_key.encode('utf-8'), 
        signed_payload.encode('utf-8'), 
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, signature):
        print(f"DEBUG: Katpay Signature Mismatch! Expected: {expected_signature}, Got: {signature}")
        return JsonResponse({'error': 'Invalid signature'}, status=401)

    # 2. Replay attack protection
    import time
    try:
        if abs(time.time() - float(timestamp)) > 3600: # Increased to 1 hour for debugging
            print(f"DEBUG: Katpay Webhook - Timestamp too old. Now: {time.time()}, Sent: {timestamp}")
            return JsonResponse({'error': 'Timestamp too old'}, status=401)
    except Exception as e:
        print(f"DEBUG: Timestamp parsing failed: {e}")
        pass
        
    try:
        data = json.loads(payload)
        print(f"DEBUG: Parsed JSON Data: {json.dumps(data, indent=2)}")
    except Exception as e:
        print(f"DEBUG: Katpay Webhook - Invalid JSON: {e}")
        return HttpResponse(status=400)
        
    event_type = data.get('event_type') or data.get('event')
    print(f"DEBUG: Event Type detected: {event_type}")
    
    if event_type == 'virtual_account.payment_received':
        data_obj = data.get('data', {})
        transaction = data_obj.get('transaction', {})
        customer = data_obj.get('customer', {})
        virtual_account = data_obj.get('virtual_account', {})
        
        # Extract details
        account_number = virtual_account.get('account_number') or virtual_account.get('accountNumber')
        amount_raw = transaction.get('order_amount', transaction.get('amount', 0))
        amount = Decimal(str(amount_raw))
        reference = transaction.get('reference', transaction.get('order_no', transaction.get('id', '')))
        customer_email = customer.get('email')
        
        print(f"DEBUG: Extracted -> Acct: {account_number}, Amount: {amount}, Ref: {reference}, Email: {customer_email}")
        
        user = None
        try:
            if account_number:
                account_number = str(account_number).strip()
                profile = Profile.objects.filter(virtual_account_number=account_number).first()
                if not profile:
                    # Try fuzzy matching (with/without leading zero)
                    if account_number.startswith('0'):
                        profile = Profile.objects.filter(virtual_account_number=account_number[1:]).first()
                    else:
                        profile = Profile.objects.filter(virtual_account_number='0' + account_number).first()
                
                if profile:
                    user = profile.user
                    print(f"DEBUG: Profile found! User: {user.username}")
            
            if not user and customer_email:
                user = User.objects.filter(email__iexact=customer_email).first()
                if user:
                    print(f"DEBUG: User found via email fallback: {user.username}")

            if not user:
                print(f"DEBUG: FAILED - No user found for Acct {account_number} or Email {customer_email}")
                return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)
        except Exception as e:
            print(f"DEBUG: Exception during user lookup: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
            
        if user:
            # IMPORTANT: For webhooks, the 'event_id' is the most reliable unique identifier 
            # for each specific payment notification. Some payment references (like name:phone) 
            # might be static and cause false duplicate detections.
            unique_ref = data.get('event_id') or reference
            
            print(f"DEBUG: Checking for duplicate reference: {unique_ref}")
            
            existing_txn = Transaction.objects.filter(reference=unique_ref, service='wallet_funding').exists()
            if not existing_txn:
                charge = Decimal('3.00')
                net_amount = amount - charge
                if net_amount < 0: net_amount = 0
                
                old_balance = user.wallet
                user.wallet += net_amount
                user.save()
                
                # Also update profile wallet just in case
                profile = Profile.objects.filter(user=user).first()
                if profile:
                    profile.wallet += net_amount
                    profile.save()
                
                print(f"DEBUG: !!! FUNDING SUCCESS !!!")
                print(f"DEBUG: User: {user.username}")
                print(f"DEBUG: Old Balance: {old_balance}")
                print(f"DEBUG: Gross Amount: {amount}")
                print(f"DEBUG: Charge: {charge}")
                print(f"DEBUG: Net Amount: {net_amount}")
                print(f"DEBUG: New Balance: {user.wallet}")
                print(f"DEBUG: Reference: {unique_ref}")
                
                Transaction.objects.create(
                    user=user,
                    service='wallet_funding',
                    amount=net_amount,
                    status='success',
                    description=f'Wallet funded via static VA (Gross: ₦{amount}, Charge: ₦{charge})',
                    reference=unique_ref
                )
            else:
                print(f"DEBUG: SKIPPED - Reference {unique_ref} already exists in Transactions.")
        
        return JsonResponse({'status': 'success', 'message': 'Payment processed'}, status=200)
        
    elif event_type == 'transfer_payment.completed':
        payment = data.get('data', {})
        reference = payment.get('merchant_reference')
        amount = Decimal(str(payment.get('amount', 0)))
        
        try:
            dva = DynamicVirtualAccount.objects.get(reference=reference, status='active')
            user = dva.user
            
            charge = Decimal('3.00')
            net_amount = amount - charge
            if net_amount < 0: net_amount = 0
            
            old_balance = user.wallet
            user.wallet += net_amount
            user.save()
            
            print(f"DEBUG: DYNAMIC FUNDING SUCCESS - User: {user.username}, Old Balance: {old_balance}, New Balance: {user.wallet}, Gross: {amount}, Charge: {charge}, Net: {net_amount}, Ref: {reference}")
            
            dva.status = 'completed'
            dva.save()
            
            Transaction.objects.create(
                user=user,
                service='wallet_funding',
                amount=net_amount,
                status='success',
                description=f'Wallet funded via dynamic VA (Gross: ₦{amount}, Charge: ₦{charge})',
                reference=reference
            )
        except DynamicVirtualAccount.DoesNotExist:
            print(f"DEBUG: Webhook dynamic VA lookup failed for reference: {reference}")
            pass
            
        print("DEBUG: Katpay Webhook - Sending SUCCESS response (Dynamic VA)")
        return JsonResponse({'status': 'success'}, status=200)
            
    print(f"DEBUG: Katpay Webhook - Sending default SUCCESS response for unhandled event: {event_type}")
    return JsonResponse({'status': 'success'}, status=200)

@login_required
@require_POST
def admin_update_payment_methods(request):
    err = _admin_required(request)
    if err: return err
    
    enable_static_va = request.POST.get('enable_static_va') == 'true'
    enable_dynamic_va = request.POST.get('enable_dynamic_va') == 'true'
    
    settings = SiteSetting.load()
    settings.enable_static_va = enable_static_va
    settings.enable_dynamic_va = enable_dynamic_va
    settings.save()
    
    return JsonResponse({'success': True, 'message': 'Payment methods updated'})



@login_required
def referral_dashboard_view(request):
    """View for the comprehensive referral dashboard."""
    user = request.user
    referred_users = user.referrals.all().order_by('-date_joined')
    
    # Total earnings
    total_earnings = ReferralBonus.objects.filter(beneficiary=user).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    level1_earnings = ReferralBonus.objects.filter(beneficiary=user, level=1).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    level2_earnings = ReferralBonus.objects.filter(beneficiary=user, level=2).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
    
    # Earnings history
    earnings_history = ReferralBonus.objects.filter(beneficiary=user).select_related('source_user', 'transaction').order_by('-created_at')
    
    # Conversion rate (simplistic: active users / total referrals)
    total_refs = referred_users.count()
    # An active referral is one who has at least one successful transaction
    active_refs = CustomUser.objects.filter(referred_by=user, transactions__status='success').distinct().count()
    conversion_rate = int((active_refs / total_refs * 100)) if total_refs > 0 else 0
    
    # Activity log (combination of signups and bonus generation)
    # For now, let's just use ReferralBonus as activity
    activity_log = ReferralBonus.objects.filter(beneficiary=user).select_related('source_user').order_by('-created_at')[:20]
    
    # Prepare referral data with their earnings
    referrals_with_earnings = []
    for r in referred_users:
        earnings_from_r = ReferralBonus.objects.filter(beneficiary=user, source_user=r).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')
        referrals_with_earnings.append({
            'user': r,
            'earnings': earnings_from_r
        })
    
    context = {
        'total_earnings': total_earnings,
        'level1_earnings': level1_earnings,
        'level2_earnings': level2_earnings,
        'referral_count': total_refs,
        'active_referrals_count': active_refs,
        'conversion_rate': conversion_rate,
        'referral_code': user.referral_code,
        'referrals': referrals_with_earnings,
        'earnings_history': earnings_history,
        'activity_log': activity_log,
        'wallet_balance': user.wallet,
        'referral_wallet': user.referral_wallet,
    }
    
    return render(request, 'subcard_app/referral_dashboards.html', context)


@login_required
@require_POST
def withdraw_referral_to_wallet(request):
    """Transfer referral earnings to main wallet."""
    try:
        amount_str = request.POST.get('amount', '0')
        amount = Decimal(amount_str)
        user = request.user
        
        if amount < Decimal('100'):
            return JsonResponse({'success': False, 'error': 'Minimum withdrawal is ₦100'})
        
        if user.referral_wallet < amount:
            return JsonResponse({'success': False, 'error': 'Insufficient referral balance'})
        # Validate PIN
        pin_error = validate_transaction_pin(request)
        if pin_error:
            return pin_error

        
        # Perform transfer
        user.referral_wallet -= amount
        user.wallet += amount
        user.save()
        
        # Record withdrawal
        Withdrawal.objects.create(user=user, amount=amount, status='approved')
        
        return JsonResponse({
            'success': True, 
            'message': f'₦{amount:,.2f} transferred to main wallet',
            'new_referral_wallet': float(user.referral_wallet),
            'new_wallet': float(user.wallet)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
