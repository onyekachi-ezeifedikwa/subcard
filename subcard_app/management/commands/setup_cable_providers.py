from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal
from subcard_app.models import CableProvider, CablePlan


class Command(BaseCommand):
    help = 'Setup cable TV providers and plans'

    def handle(self, *args, **options):
        with transaction.atomic():
            # Create cable providers
            dstv, created = CableProvider.objects.get_or_create(
                code='dstv',
                defaults={'name': 'DSTV', 'is_active': True}
            )
            if created:
                self.stdout.write(self.style.SUCCESS('Created DSTV provider'))
            
            gotv, created = CableProvider.objects.get_or_create(
                code='gotv',
                defaults={'name': 'GOTV', 'is_active': True}
            )
            if created:
                self.stdout.write(self.style.SUCCESS('Created GOTV provider'))
            
            startimes, created = CableProvider.objects.get_or_create(
                code='startimes',
                defaults={'name': 'StarTimes', 'is_active': True}
            )
            if created:
                self.stdout.write(self.style.SUCCESS('Created StarTimes provider'))

            # DSTV Plans
            dstv_plans = [
                {'name': 'DSTV Padi', 'code': 'dstv_padi', 'price': 2500, 'duration': '1 month'},
                {'name': 'DSTV Yanga', 'code': 'dstv_yanga', 'price': 3500, 'duration': '1 month'},
                {'name': 'DSTV Confam', 'code': 'dstv_confam', 'price': 5300, 'duration': '1 month'},
                {'name': 'DSTV Compact', 'code': 'dstv_compact', 'price': 7700, 'duration': '1 month'},
                {'name': 'DSTV Compact Plus', 'code': 'dstv_compact_plus', 'price': 10500, 'duration': '1 month'},
                {'name': 'DSTV Premium', 'code': 'dstv_premium', 'price': 18000, 'duration': '1 month'},
            ]

            for plan_data in dstv_plans:
                plan, created = CablePlan.objects.get_or_create(
                    provider=dstv,
                    code=plan_data['code'],
                    defaults={
                        'name': plan_data['name'],
                        'price': plan_data['price'],
                        'duration': plan_data['duration'],
                        'is_active': True
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'Created DSTV plan: {plan_data["name"]}'))

            # GOTV Plans
            gotv_plans = [
                {'name': 'GOTV Lite', 'code': 'gotv_lite', 'price': 1100, 'duration': '1 month'},
                {'name': 'GOTV Value', 'code': 'gotv_value', 'price': 1900, 'duration': '1 month'},
                {'name': 'GOTV Max', 'code': 'gotv_max', 'price': 2700, 'duration': '1 month'},
                {'name': 'GOTV Jolli', 'code': 'gotv_jolli', 'price': 3500, 'duration': '1 month'},
                {'name': 'GOTV Supa', 'code': 'gotv_supa', 'price': 5500, 'duration': '1 month'},
            ]

            for plan_data in gotv_plans:
                plan, created = CablePlan.objects.get_or_create(
                    provider=gotv,
                    code=plan_data['code'],
                    defaults={
                        'name': plan_data['name'],
                        'price': plan_data['price'],
                        'duration': plan_data['duration'],
                        'is_active': True
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'Created GOTV plan: {plan_data["name"]}'))

            # StarTimes Plans
            startimes_plans = [
                {'name': 'StarTimes Basic', 'code': 'startimes_basic', 'price': 900, 'duration': '1 month'},
                {'name': 'StarTimes Classic', 'code': 'startimes_classic', 'price': 1300, 'duration': '1 month'},
                {'name': 'StarTimes Smart', 'code': 'startimes_smart', 'price': 2000, 'duration': '1 month'},
                {'name': 'StarTimes Nova', 'code': 'startimes_nova', 'price': 2600, 'duration': '1 month'},
                {'name': 'StarTimes Super', 'code': 'startimes_super', 'price': 4200, 'duration': '1 month'},
            ]

            for plan_data in startimes_plans:
                plan, created = CablePlan.objects.get_or_create(
                    provider=startimes,
                    code=plan_data['code'],
                    defaults={
                        'name': plan_data['name'],
                        'price': plan_data['price'],
                        'duration': plan_data['duration'],
                        'is_active': True
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(f'Created StarTimes plan: {plan_data["name"]}'))

            self.stdout.write(self.style.SUCCESS('Cable TV providers and plans setup completed!'))
